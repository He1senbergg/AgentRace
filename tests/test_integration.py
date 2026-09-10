"""Synthetic observation replay, NOT an official game/physics simulator."""
from collections import Counter
from copy import deepcopy
import json
import time
import unittest

from src import main
from test_actions import role, state, zone
from test_defense import robot


def dense_state():
    data = state(role(1, 'worker', 8, 11), role(2, 'worker', 11, 12),
                 role(3, 'pioneer', 12, 9), role(4, 'station', 10, 10, level=3),
                 role(5, 'rocket', 9, 11, level=3), role(6, 'rocket', 11, 11, level=3),
                 role(7, 'rocket', 12, 10, level=3))
    occupied = {(8, 11), (11, 12), (12, 9), (10, 10), (11, 10), (10, 9), (11, 9),
                (9, 11), (11, 11), (12, 10)}
    cells = [(x, y) for x in range(41) for y in range(32) if (x, y) not in occupied]
    data['robot'] = [robot(100 + i, x, y, 800) for i, (x, y) in enumerate(cells)]
    data['roundNo'] = 70
    return data


class IntegrationTests(unittest.TestCase):
    def test_two_halves_full_observation_replay(self):
        session = main.GameSession(origin=0)
        counts = Counter()
        maximum_seconds = 0
        for side in ('challenger', 'defender'):
            previous = main.empty_response()
            for round_no in range(1300):
                offset = round_no % 130
                data = state(role(1, 'worker', 8, 11), role(2, 'worker', 11, 12),
                             role(3, 'pioneer', 4, 5), role(4, 'station', 10, 10, level=3),
                             role(5, 'rocket', 9, 11, level=3), role(6, 'gatling', 11, 11, level=3),
                             role(7, 'railgun', 12, 10, level=3))
                # This fixed-position replay exercises economy with completed
                # defenses; construction is covered by dedicated observed-state tests.
                data['roundNo'] = round_no
                data['teamOur']['type'] = side
                data['teamOur']['roles'][3]['health'] = 4500
                data['teamOur']['roles'][0]['backpack'] = ['copper'] * (offset % 25)
                if offset in (80, 81):
                    data['teamOur']['roles'][0]['health'] = 0
                data['vendorShopList'] = [{'name': 'copper', 'price': 5}]
                zone(data, 'copper', 7, 11)
                zone(data, 'vendor', 7, 12)
                zone(data, side + 'TaskPoint2', 5, 5)
                zone(data, side + 'TaskPoint2', 5, 6)
                data['teamOur']['playerTasks'] = [dict(taskPosition=dict(x=5, y=6), isValid=True,
                                                     coldDownRounds=0, timeoutRounds=60)]
                data['phaseTask'] = ('Read the city for day %s' % (round_no // 130 + 1)
                                     if 1 <= offset <= 60 else '')
                data['worldNews'] = {'officialNews': '第%s天平静。' % (round_no // 130 + 1)}
                if previous['prompt'].startswith('Solve only'):
                    data['llmResp'] = json.dumps({'command': 'python --version'} if offset % 4 == 2
                                                 else {'answer': 'Beijing', 'skill': 'Inspect then extract city'})
                elif previous['prompt']:
                    data['llmResp'] = '{"events":[],"treasure":null}'
                if previous['executeCmd']:
                    data['lastCmdResult'] = '[exitCode:0]\nPython 3.11.10'
                # No physical actions are simulated; failure results avoid inventing
                # successful movement/collection while the observed positions stay fixed.
                data['lastRoundRoleActionResults'] = {i: False for i in previous['roleCommandMap']}
                if offset >= 70:
                    data['robot'] = [robot(100+i, 14+i % 4, 10+i // 4, side=side) for i in range(12)]
                start = time.monotonic()
                response = session.handle(data)
                maximum_seconds = max(maximum_seconds, time.monotonic() - start)
                self.assertEqual(set(response), {'roleCommandMap', 'prompt', 'executeCmd'})
                self.assertLessEqual(session.memory.llm_calls_today, 3)
                self.assertLessEqual(len(session.memory.news), 10)
                self.assertLessEqual(len(session.memory.task_experience), 16)
                if session.memory.task:
                    self.assertLessEqual(len(session.memory.task['history']), 8)
                if response['executeCmd']:
                    self.assertTrue(data['phaseTask'])
                    counts['sandbox'] += 1
                if response['prompt']:
                    counts['prompt'] += 1
                actors = set(response['roleCommandMap'])
                controllers = []
                for actor, command in response['roleCommandMap'].items():
                    counts[command['action']] += 1
                    if command['action'] == 'attack':
                        self.assertGreaterEqual(offset, 70)
                        controllers.append(command['controllerId'])
                        self.assertNotIn(command['controllerId'], actors)
                    for pos in command.get('targetPos', []):
                        self.assertTrue(0 <= pos['x'] <= 40 and 0 <= pos['y'] <= 31)
                self.assertEqual(len(controllers), len(set(controllers)))
                if offset in (0, 60, 70, 129):
                    before = deepcopy(session.memory)
                    self.assertEqual(session.handle(data), response)
                    self.assertEqual(session.memory, before)
                json.dumps(response, ensure_ascii=False, allow_nan=False).encode('utf-8')
                previous = response
            self.assertEqual(session.memory.phase.day, 10)
        for action in ('acceptTask', 'submitAnswer', 'attack', 'collect', 'sell', 'sandbox'):
            self.assertGreater(counts[action], 0, counts)
        self.assertLess(maximum_seconds, 1)

    def test_malformed_optional_fields_do_not_collapse_planning(self):
        baseline = state(role(1, 'worker', 5, 5), vendorShopList=[{'name': 'iron', 'price': 3}])
        zone(baseline, 'iron', 6, 5)
        for field in ('robot', 'teamEnemy', 'worldNews', 'errors', 'llmResp', 'lastCmdResult', 'phaseTask'):
            for bad in (None, True, 42, [], {'unexpected': []}):
                data = deepcopy(baseline)
                data[field] = bad
                response = main.GameSession().handle(data)
                self.assertEqual(response['roleCommandMap']['1']['action'], 'collect', (field, bad))
