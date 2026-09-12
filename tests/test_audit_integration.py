"""Default defense lifecycle contracts on synthetic observations, without combat simulation."""
from collections import Counter
from copy import deepcopy
import json
import time
import unittest

from src import main3 as main
from test_actions import state, zone
from test_defense import robot


def lifecycle_role(actor, kind, x, y, health, **fields):
    return dict(id=actor, roleType=kind, pos=dict(x=x, y=y), health=health,
                backpack=[], **fields)


def lifecycle_observation(index, origin, side):
    day, offset = divmod(index, 130)
    data = state(lifecycle_role(1, 'worker', 8, 11, health=220),
                 lifecycle_role(2, 'worker', 11, 12, health=220),
                 lifecycle_role(3, 'pioneer', 4, 5, health=200),
                 lifecycle_role(4, 'station', 10, 10, health=4500, level=3),
                 lifecycle_role(5, 'rocket', 9, 11, health=2000, level=3),
                 lifecycle_role(6, 'railgun', 11, 11, health=2000, level=3),
                 lifecycle_role(7, 'rocket', 12, 10, health=2000, level=3))
    data['roundNo'] = index + origin
    data['teamOur'].update(type=side, goldNum=0)
    roles = data['teamOur']['roles']
    roles[0]['backpack'] = ['copper'] * (offset % 25)
    wall_cells = [(13, y) for y in range(7, 13)] + [(x, 7) for x in range(8, 12)]
    roles.extend(lifecycle_role(40000+i, 'wall', x, y, health=2000, level=3)
                 for i, (x, y) in enumerate(wall_cells))
    # Persistent losses test stale ownership across later nights/days. No action
    # output is treated as an executed move, purchase, or kill.
    if index >= 3 * 130 + 80:
        roles[:] = [r for r in roles if r['id'] != 2]
    if index >= 5 * 130 + 90:
        roles[:] = [r for r in roles if r['id'] != 6]
    if index >= 1290:
        roles.clear()
    zone(data, 'vendor', 7, 12)
    zone(data, 'copper', 7, 11)
    zone(data, side + 'TaskPoint2', 5, 5)
    zone(data, side + 'TaskPoint2', 5, 6)
    data['vendorShopList'] = [dict(name='copper', price=5)]
    data['teamOur']['playerTasks'] = [dict(taskPosition=dict(x=5, y=6), isValid=True,
                                               coldDownRounds=0, timeoutRounds=20)]
    data['phaseTask'] = f'Read the city for day {day + 1}' if 1 <= offset <= 12 else ''
    data['worldNews'] = dict(officialNews=f'Day {day + 1}')
    if offset >= 70:
        data['robot'] = [robot(100+i, 14+i % 3, 10+i // 3, side=side) for i in range(9)]
        # Observed cooldowns, independent of our output, include all firing windows.
        for r in roles:
            if r['roleType'] == 'rocket':
                r['cooldown'] = offset % 3
    if side == 'defender':
        for obj in [*roles, *data['mapInfo']['zones'], *data.get('robot', [])]:
            x, y = obj['pos']['x'], obj['pos']['y']
            obj['pos'] = dict(x=39-x, y=32-y) if obj.get('roleType') == 'station' else dict(x=40-x, y=31-y)
        for task in data['teamOur']['playerTasks']:
            x, y = task['taskPosition']['x'], task['taskPosition']['y']
            task['taskPosition'] = dict(x=40-x, y=31-y)
    return data


class DefaultDefenseLifecycleTests(unittest.TestCase):
    def test_default_defense_two_halves_full_lifecycle(self):
        session = main.GameSession()
        self.assertEqual(session.strategy_mode, 'defense')
        maximum_seconds = 0.0
        for side, origin in (('challenger', 0), ('defender', 1)):
            counts = Counter()
            previous = main.empty_response()
            for index in range(1300):
                data = lifecycle_observation(index, origin, side)
                offset = index % 130
                if previous['prompt'].startswith('Solve only'):
                    data['llmResp'] = json.dumps({'command': 'python --version'} if offset % 4 == 2
                                                 else {'answer': 'Beijing', 'skill': 'Inspect city'})
                elif previous['prompt']:
                    data['llmResp'] = '{"events":[],"treasure":null}'
                if previous['executeCmd']:
                    data['lastCmdResult'] = '[exitCode:0]\nPython 3.11.10'
                data['lastRoundRoleActionResults'] = {actor: False for actor in previous['roleCommandMap']}
                started = time.monotonic()
                response = session.handle(data)
                maximum_seconds = max(maximum_seconds, time.monotonic() - started)
                memory = session.memory
                self.assertEqual(memory.last_round, index + origin)
                self.assertEqual(memory.phase.round_in_day, offset + 1)
                self.assertEqual(memory.origin, origin)
                self.assertEqual(set(response), {'roleCommandMap', 'prompt', 'executeCmd'})
                self.assertEqual(memory.previous_actions, response['roleCommandMap'])
                self.assertLessEqual(memory.llm_calls_today, 3)
                self.assertLessEqual(len(memory.task_experience), 16)
                if not data['phaseTask']:
                    self.assertIsNone(memory.task)
                live = {str(r['id']): r for r in data['teamOur']['roles']}
                self.assertTrue(set(memory.strategic.plan.jobs) <= set(live))
                self.assertTrue(set(memory.strategic.plan.controllers) <= set(live))
                if response['executeCmd']:
                    self.assertTrue(data['phaseTask'])
                    counts['sandbox'] += 1
                used = set(response['roleCommandMap'])
                targets = set()
                for actor, command in response['roleCommandMap'].items():
                    self.assertIn(actor, live)
                    counts[command['action']] += 1
                    if command['action'] == 'attack':
                        self.assertGreaterEqual(offset, 70)
                        self.assertEqual(live[actor].get('cooldown', 0), 0)
                        controller = command['controllerId']
                        self.assertNotIn(controller, used)
                        self.assertIn(controller, live)
                        used.add(controller)
                    if command['action'] == 'move':
                        destination = tuple(command['targetPos'][0][k] for k in ('x', 'y'))
                        self.assertNotIn(destination, targets)
                        targets.add(destination)
                json.dumps(response, ensure_ascii=False, allow_nan=False).encode('utf-8')
                if offset in (0, 12, 69, 70, 129):
                    before = deepcopy(memory)
                    self.assertEqual(session.handle(deepcopy(data)), response)
                    self.assertEqual(session.memory, before)
                previous = response
            self.assertEqual(session.memory.phase.day, 10)
            self.assertFalse(session.memory.strategic.plan.jobs)
            for action in ('attack', 'submitAnswer', 'sandbox'):
                self.assertGreater(counts[action], 0, (side, counts))
        self.assertLess(maximum_seconds, 5, 'AI Spec §62: response deadline')


if __name__ == '__main__':
    unittest.main()
