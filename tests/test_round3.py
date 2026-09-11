"""Round3 factual geometry fixtures and bounded V2.1 Shadow contracts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import main3 as main
from src.agentrace import strategy
from tools.decode_match2 import decode
from test_actions import role, state, zone
from test_shadow import shadow

ROOT = Path(__file__).resolve().parents[1]


def defense_day(day=2):
    data = state(role(1, 'worker', 8, 21), role(2, 'worker', 7, 22), role(3, 'pioneer', 7, 23),
                 role(9, 'station', 9, 22, level=1), role(10, 'rocket', 9, 20, level=2),
                 role(11, 'rocket', 8, 22, level=1), role(12, 'rocket', 8, 23, level=1))
    data['roundNo'] = (day - 1) * 130 + 1
    data['teamOur']['goldNum'] = 250
    data['weaponShopList'] = [dict(name=n, price=p) for n, p in [('WallFixer', 10), ('WallUpgradeVoucher1', 20),
                                                             ('WeaponUpgradeVoucher1', 100)]]
    zone(data, 'weaponShop', 7, 21)
    zone(data, 'stone', 13, 23)
    return data


class Round3Tests(unittest.TestCase):
    def test_real_r331_geometry_matching_and_no_three_person_move(self):
        for game in ('game9', 'game10'):
            f = json.loads((ROOT / 'tests/fixtures' / f'round3_{game}_r331.json').read_text(encoding='utf-8'))
            data = state(*f['roles'])
            data['roundNo'] = 331
            world = main.World(data)
            memory = main.GameMemory((7, 'challenger'), 1)
            delta = memory.observe(world, 331)
            planner = main.StrategicPlanner(world, memory, delta, main.Rules())
            actual = {a['id']: {k: v for k, v in a.items() if k in {'action', 'controllerId', 'targetPos'}}
                      for a in f['legacy_actions'] if a['action'] == 'attack'}
            # The log omits robot positions/HP. Inject only recorded target commands,
            # testing controller coverage, not inventing or verifying attack scoring.
            def recorded_target(weapon):
                c = actual.get(weapon['id'])
                return ([(p['x'], p['y']) for p in c['targetPos']], {}, 1) if c else ([], {}, 0)
            with patch.object(planner.defense, 'attack_plan', recorded_target):
                _, report = planner.run(dict(main.empty_response(), roleCommandMap=actual))
            self.assertGreaterEqual(report['metrics']['adjacent_controller_matching_size'], len(actual))
            self.assertGreaterEqual(sum(c['action'] == 'attack' for c in planner.v.commands.values()), len(actual))
            self.assertFalse(any(c['action'] == 'move' for c in planner.v.commands.values()))

    def test_matching_uses_augmenting_path_and_cooldown_does_not_own_controller(self):
        data = state(role(1, 'worker', 11, 10), role(2, 'worker', 9, 10),
                     role(10, 'rocket', 10, 10, level=1), role(11, 'rocket', 12, 10, level=1))
        p, _, _ = shadow(data)
        self.assertEqual(p.adjacent_matching(), {'10': '2', '11': '1'})
        p.world.roles['10']['cooldown'] = 3
        self.assertEqual(p.adjacent_matching(), {'11': '1'})

    def test_static_deadline_ignores_transient_occupancy(self):
        data = defense_day(1)
        p, _, _ = shadow(data)
        job = main.RoleJob('1', 'BUILD_WALL', None, 'START', 70, 1, 70)
        before = p.completion_trip(job, (8, 21))
        self.assertIsNotNone(before)
        p.world.occupied.update(main.neighbors((8, 21)))
        self.assertEqual(p.completion_trip(job, (8, 21)), before)

    def test_benchmark_never_follows_execution_downgrade(self):
        data = defense_day(1)
        def estimate(planner, job, slot):
            return (100, 1) if job.job_type == 'BUILD_WALL' and planner.plan.execution_wall_target > 4 else (1, 1)
        with patch.object(strategy.StrategicPlanner, 'completion_trip', estimate):
            p, _, report = shadow(data)
        self.assertEqual((p.plan.benchmark_wall_target, p.plan.execution_wall_target, p.plan.unmet_wall_target), (8, 4, 4))
        self.assertIn('DEADLINE_INFEASIBLE', report['reasons'])

    def test_new_day_discards_night_jobs_and_retains_wall_history(self):
        data = defense_day(1)
        data['roundNo'] = 130
        memory = main.GameMemory((7, 'challenger'), 1)
        _, memory, _ = shadow(data, memory)
        memory.strategic.plan.mode = 'PRE_NIGHT'
        memory.strategic.plan.jobs['1'] = main.RoleJob('1', 'RETURN', None, 'HOLD', 100, 129, 260)
        memory.strategic.wall_damage['20'] = 300
        data['roundNo'] = 131
        data['teamOur']['roles'].append(dict(role(20, 'wall', 12, 22, level=1), health=700))
        p, _, report = shadow(data, memory)
        self.assertIn('NEW_DAY', report['reasons'])
        self.assertEqual(p.plan.day, 2)
        self.assertNotEqual(p.plan.mode, 'PRE_NIGHT')
        self.assertTrue(all(j.job_type not in {'CONTROL', 'RETURN'} for j in p.plan.jobs.values()))
        self.assertEqual(p.state.wall_damage['20'], 300)

    def test_day2_wall_service_precedes_upgrade_and_day3_targets(self):
        data = defense_day(2)
        data['teamOur']['roles'].append(dict(role(20, 'wall', 12, 22, level=1), health=500))
        p, _, report = shadow(data, main.GameMemory((7, 'challenger'), 1))
        self.assertEqual(p.plan.benchmark_wall_target, 9)
        self.assertEqual(p.plan.wall_hp_target, 8000)
        self.assertTrue(any(j.job_type == 'WALL_SERVICE' for j in p.plan.jobs.values()))
        self.assertTrue(any(c.get('name') == 'WallUpgradeVoucher1' for c in p.v.commands.values()))
        self.assertGreater(p.plan.budget.committed_gold, 0)
        data['roundNo'] = 261
        p, _, report = shadow(data, main.GameMemory((7, 'challenger'), 1))
        self.assertEqual((p.plan.benchmark_wall_target, p.plan.wall_hp_target, p.plan.weapon_level_target), (10, 10000, (2, 2, 1)))
        self.assertFalse(any(c.get('name') == 'WeaponUpgradeVoucher2' for c in p.v.commands.values()))
        self.assertFalse(report['metrics']['day1_benchmark_met'])

    def test_night_wall_disappearance_is_not_invented_kill(self):
        data = defense_day(1)
        data['roundNo'] = 71
        data['teamOur']['roles'].append(dict(role(20, 'wall', 12, 22, level=1), health=700))
        _, memory, _ = shadow(data, main.GameMemory((7, 'challenger'), 1))
        data['roundNo'] = 72
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles'] if r['id'] != 20]
        _, _, report = shadow(data, memory)
        metrics = report['metrics']
        self.assertEqual(metrics['wall_ids_missing_since_night_start'], ['20'])
        self.assertIsNone(metrics['wall_destroyed_since_night_start'])
        self.assertEqual(metrics['wall_total_hp'], 0)
        self.assertNotIn('kills', metrics)

    def test_redundant_characters_recover_physical_coverage_even_during_cooldown(self):
        data = state(role(1, 'worker', 8, 19), role(2, 'worker', 9, 19), role(3, 'pioneer', 10, 19),
                     role(9, 'station', 9, 22, level=1), role(10, 'rocket', 9, 20, level=1, cooldown=3),
                     role(11, 'rocket', 8, 23, level=1, cooldown=3), role(12, 'rocket', 11, 23, level=1, cooldown=3))
        data['roundNo'] = 71
        p, _, report = shadow(data, main.GameMemory((7, 'challenger'), 1))
        self.assertEqual(report['metrics']['adjacent_controller_matching_size'], 1)
        self.assertEqual(report['metrics']['ready_weapon_matching_size'], 0)
        self.assertTrue(any(c['action'] == 'move' for c in p.v.commands.values()))
        self.assertNotIn('1', p.v.commands)  # Preserve the character already providing coverage.

    def test_decode_all_three_logs_and_reject_corruption(self):
        for game, expected in [('game8', 194), ('game9', 189), ('game10', 188)]:
            path = next((ROOT / 'log/Versus/round3' / game).glob('enemy*'))
            self.assertEqual(len(decode(path)), expected)
        line = next(line for line in path.read_text(encoding='utf-8').splitlines() if line.startswith('MATCH2 '))
        fields = line.split()
        fields[8] = '0' * 64
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / 'bad.log'
            broken.write_text(' '.join(fields), encoding='utf-8')
            with self.assertRaises(ValueError):
                decode(broken)
