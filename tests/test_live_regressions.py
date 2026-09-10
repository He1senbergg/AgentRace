"""Regressions motivated by Self/1.log; fixtures are not an official simulator."""
import unittest
from src import main3 as main
from test_actions import role, state, zone
from test_defense import robot


class LiveRegressionTests(unittest.TestCase):
    def test_one_based_opening_builds_and_reaches_first_night(self):
        data = state(role(20010, 'worker', 30, 8), role(20011, 'pioneer', 32, 8),
                     role(20012, 'worker', 31, 8), role(20013, 'station', 30, 10, level=1))
        session = main.GameSession()
        built = 0
        # Apply only legal movement/construction, with no fabricated combat result.
        for turn in range(1, 72):
            data['roundNo'] = turn
            if turn == 71:
                data['robot'] = [robot(30000, 29, 7, health=400)]
            result = session.handle(data)
            self.assertEqual(session.memory.phase.is_day, turn <= 70)
            if turn == 8:
                self.assertEqual(built, 3)  # Allow short relocation to the facing side.
            if turn == 71:
                self.assertIn('attack', [c['action'] for c in result['roleCommandMap'].values()])
            by_id = {str(r['id']): r for r in data['teamOur']['roles']}
            for actor, command in result['roleCommandMap'].items():
                if command['action'] == 'move':
                    by_id[actor]['pos'] = command['targetPos'][0]
                elif command['action'] == 'build':
                    pos = command['targetPos'][0]
                    built += 1
                    data['teamOur']['roles'].append(role(21000 + built, command['name'], pos['x'], pos['y'], level=1))
                    data['teamOur']['goldNum'] -= 25
        self.assertEqual(built, 3)
        self.assertEqual(data['teamOur']['goldNum'], 0)

    def test_origin_midgame_and_explicit_zero(self):
        session = main.GameSession()
        data = state()
        data['roundNo'] = 5
        session.handle(data)
        self.assertIsNone(session.memory.phase)
        zero = main.GameSession(origin=0)
        data['roundNo'] = 1
        zero.handle(data)
        self.assertEqual(zero.memory.phase, main.Phase(1, 2))
        data['roundNo'] = 70
        zero.handle(data)
        self.assertFalse(zero.memory.phase.is_day)

    def test_new_task_cannot_take_night_gunner(self):
        data = state(role(1, 'pioneer', 9, 10), role(2, 'gatling', 10, 10, level=1),
                     robot=[robot(50, 10, 12)])
        zone(data, 'challengerTaskPoint1', 8, 10)
        data['teamOur']['playerTasks'] = [dict(taskPosition=dict(x=8, y=10), isValid=True,
                                               coldDownRounds=0, timeoutRounds=20)]
        data['roundNo'] = 71
        response = main.GameSession(origin=1).handle(data)
        self.assertEqual(response['roleCommandMap']['2']['action'], 'attack')
        self.assertNotIn('1', response['roleCommandMap'])
        # Active task owners remain unavailable for defense.
        data['phaseTask'] = 'SECRET'
        response = main.GameSession(origin=1).handle(data)
        self.assertNotIn('2', response['roleCommandMap'])

    def test_map_axes_footprints_and_no_external_text(self):
        data = state(role(1, 'worker', 0, 31), role(2, 'station', 30, 10),
                     teamEnemy={'roles': [role(3, 'pioneer', 40, 0)]},
                     robot=[robot(50, 4, 5)])
        zone(data, 'vendor', 7, 8)
        zone(data, 'SECRET', 6, 6)
        output = main.render_map(main.World(data))
        rows = {int(line[:2]): line[4:] for line in output.splitlines() if line[:2].isdigit()}
        self.assertEqual(len(rows), 32)
        self.assertTrue(all(len(row) == 41 for row in rows.values()))
        self.assertEqual(rows[31][0], 'W')
        self.assertEqual(rows[0][40], 'p')
        for y in (9, 10):
            self.assertEqual(rows[y][30:32], 'BB')
        self.assertEqual(rows[8][7], 'V')
        self.assertEqual(rows[5][4], 'R')
        self.assertNotIn('SECRET', output)
