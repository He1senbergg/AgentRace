"""Specification regressions for the static combat audit; no battle simulation."""
from copy import deepcopy
from fractions import Fraction
import time
import unittest

from src import main3 as main
from test_actions import role, state, target, validator
from test_defense import robot
from test_round5 import production, setup


class CombatAuditTests(unittest.TestCase):
    def test_ballistic_crossed_cell_intercepts_before_off_axis_target(self):
        # The segment crosses (11, 10)'s interior although its center is off-axis.
        for kind, expected in [('gatling', {'50': 5}),
                               ('railgun', {'50': 5, '51': 15})]:
            data = state(role(10, kind, 10, 10, level=2),
                         robot=[robot(50, 11, 10, 5, 'defender'), robot(51, 13, 11)])
            d = main.DefensePlanner(validator(data, main.Phase(1, 71)))
            self.assertEqual(d.damage(d.weapons[0], (13, 11)), expected)

    def test_ballistic_grid_interior_matches_independent_fraction_clipping(self):
        # Independent slab clipping, all quadrants, steep/shallow/axis directions.
        # Strict interior overlap excludes ambiguous edge/corner-only contacts.
        def crosses(dx, dy, x, y):
            start, end = Fraction(0), Fraction(1)
            for velocity, center in ((dx, x), (dy, y)):
                if velocity == 0:
                    if center != 0:
                        return False
                    continue
                a, b = sorted((Fraction(2 * center - 1, 2 * velocity),
                               Fraction(2 * center + 1, 2 * velocity)))
                start, end = max(start, a), min(end, b)
            return start < end

        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if (dx, dy) == (0, 0):
                    continue
                for x in range(-5, 6):
                    for y in range(-5, 6):
                        if (x, y) == (0, 0):
                            continue
                        data = state(role(10, 'railgun', 10, 10, level=1),
                                     robot=[robot(50, 10 + x, 10 + y)])
                        d = main.DefensePlanner(validator(data, main.Phase(1, 71)))
                        self.assertEqual(bool(d.damage(d.weapons[0], (10 + dx, 10 + dy))),
                                         crosses(dx, dy, x, y), (dx, dy, x, y))

    def test_ballistic_prediction_filters_dead_and_stops_at_endpoint(self):
        data = state(role(10, 'railgun', 10, 10, level=3),
                     robot=[robot(50, 11, 10, 5), robot(51, 12, 11, 5),
                            robot(52, 13, 11, 5), robot(53, 14, 11, 40),
                            robot(54, 9, 10, 40), robot(55, 11, 11, 40)])
        d = main.DefensePlanner(validator(data, main.Phase(1, 71)))
        d.remaining['50'] = 0
        self.assertEqual(d.damage(d.weapons[0], (13, 11)), {'51': 5, '52': 5})

    def test_intercepting_robot_prevents_wasting_legacy_gatling_volley(self):
        data = state(role(1, 'worker', 9, 10), role(10, 'gatling', 10, 10, level=1),
                     robot=[robot(50, 11, 10, 40, 'defender'), robot(51, 13, 11)])
        data['roundNo'] = 70
        session = main.GameSession(origin=0, strategy_mode='legacy')
        response = session.handle(data)
        self.assertFalse(any(c['action'] == 'attack' for c in response['roleCommandMap'].values()))
        self.assertEqual(session.handle(deepcopy(data)), response)

    def test_dense_ballistic_callback_stays_within_existing_four_second_budget(self):
        data = state(role(1, 'worker', 19, 14), role(2, 'worker', 21, 14),
                     role(3, 'pioneer', 20, 16),
                     role(10, 'gatling', 19, 15, level=3, attackRange=40),
                     role(11, 'railgun', 20, 15, level=3, attackRange=40),
                     role(12, 'railgun', 21, 15, level=3, attackRange=40),
                     robot=[robot(100 + i, i % 20, i // 20, 800) for i in range(200)])
        data['roundNo'] = 70
        session = main.GameSession(origin=0, strategy_mode='legacy')
        start = time.monotonic()
        response = session.handle(data)
        self.assertEqual(len(response['roleCommandMap']), 3)
        self.assertTrue(all(c['action'] == 'attack' for c in response['roleCommandMap'].values()))
        self.assertEqual(response, session.handle(deepcopy(data)))
        self.assertLess(time.monotonic() - start, 4.0)

    def test_rocket_damage_at_map_corners_and_stacked_robots(self):
        for x, y, nx, ny in [(0, 0, 1, 1), (40, 0, 39, 1),
                             (0, 31, 1, 30), (40, 31, 39, 30)]:
            data = state(role(10, 'rocket', 20, 15, level=3),
                         robot=[robot(50, x, y, 7), robot(51, x, y, 40),
                                robot(52, nx, ny, 40), robot(53, 20, 16, 40)])
            for cls in (main.DefensePlanner, main.ShadowDefensePlanner):
                d = cls(validator(data, main.Phase(1, 71)))
                self.assertEqual(d.damage(d.weapons[0], (x, y)),
                                 {'50': 7, '51': 20, '52': 10})

    def test_invalid_attack_leaves_controller_available_and_ledger_unchanged(self):
        data = state(role(1, 'worker', 9, 10), role(10, 'rocket', 10, 10, level=1))
        for extra in ({'cooldown': 1}, {'cooldown': -1}, {'cooldown': True},
                      {'cooldown': None}, {'attackRange': False}, {'health': 0}):
            altered = deepcopy(data)
            altered['teamOur']['roles'][1].update(extra)
            v = validator(altered, main.Phase(1, 71))
            before = (v.gold, v.weapon_count, v.wall_count, v.summons)
            self.assertFalse(v.add('10', target('attack', 11, 10, controllerId='1')))
            self.assertEqual((v.commands, v.busy, v.targets, v.modified), ({}, set(), set(), set()))
            self.assertEqual((v.gold, v.weapon_count, v.wall_count, v.summons), before)
            self.assertTrue(v.add('1', target('move', 8, 10)))

    def test_growth_rebuilds_missing_weapon_type(self):
        for survivors, expected in [(('rocket', 'railgun'), 'rocket'),
                                    (('rocket', 'rocket'), 'railgun'),
                                    (('railgun',), 'rocket')]:
            data = state(role(1, 'worker', 7, 22), role(9, 'station', 9, 22, level=1),
                         *[role(10 + i, kind, 8, 21 + i, level=1)
                           for i, kind in enumerate(survivors)])
            d = main.DefensePlanner(validator(data), growth_mode=True)
            self.assertTrue(d.construct())
            self.assertEqual(d.v.commands['1']['name'], expected)

    def test_production_rebuild_counts_survivors_and_same_turn_builds(self):
        data = production(131, 50)
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles']
                                   if r['roleType'] != 'rocket' or r['id'] == 10]
        survivor = next(r for r in data['teamOur']['roles'] if r['id'] == 10)
        survivor['roleType'] = 'railgun'
        data['teamOur']['roles'][0]['pos'] = dict(x=7, y=21)
        data['teamOur']['roles'][1]['pos'] = dict(x=7, y=23)
        p = setup(data)
        for actor in ('1', '2'):
            p.execute_job(p.plan.jobs[actor], main.empty_response())
        self.assertEqual([p.v.commands[a]['name'] for a in ('1', '2')], ['rocket', 'rocket'])


if __name__ == '__main__':
    unittest.main()
