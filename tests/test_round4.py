"""Round4 observed checkpoints in controlled geometry, not a combat simulator.

The logs do not contain complete observations at every round. HP, gold and
levels below are recorded checkpoint facts; positions/shop are test geometry.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src import main3 as main
from test_actions import role, zone
from test_round3 import defense_day
from test_shadow import shadow


def checkpoint(game=12, round_no=131, gold=None):
    data = defense_day(2 if round_no <= 260 else 3)
    data['roundNo'] = round_no
    hp = {131: [735, 775, 875, 895, 390, 1000, 650, 525],
          260: [490, 625, 790, 560, 175, 945, 430, 835],
          330: [1000, 625, 790, 560, 1000, 945, 1000, 835]}[round_no]
    data['teamOur']['goldNum'] = gold if gold is not None else (197 if game == 11 else {131: 35, 260: 10, 330: 56}[round_no])
    for r in data['teamOur']['roles']:
        if r['roleType'] == 'station':
            r['health'] = 920 if game == 11 else 1345 if round_no == 131 else 1250
        elif r['roleType'] == 'worker':
            r['health'] = (180 if r['id'] == 1 else 220) if game == 11 else (120 if round_no == 131 else 75) if r['id'] == 1 else (220 if round_no == 131 else 205)
        elif r['roleType'] == 'pioneer':
            r['health'] = 200
        elif r['roleType'] == 'rocket':
            r['health'] = 1500 if r['level'] == 2 else 1000
            if game == 12 and round_no == 131:
                r['level'] = 1
                r['health'] = 1000
    if game == 12:
        for i, health in enumerate(hp):
            data['teamOur']['roles'].append(dict(role(20 + i, 'wall', 12, 18 + i, level=1), health=health))
    data['weaponShopList'] += [dict(name=n, price=p) for n, p in
                              [('Medicine', 10), ('WallUpgradeVoucher2', 30),
                               ('WeaponUpgradeVoucher2', 150), ('StationUpgradeVoucher1', 100)]]
    return data


def plan(data):
    return shadow(data, main.GameMemory((7, 'challenger'), 1))


class Round4Tests(unittest.TestCase):
    def test_unfunded_services_earn_without_abandoning_jobs(self):
        data = checkpoint(gold=0)
        data['roundNo'] = 261
        data['vendorShopList'] = [dict(name='copper', price=5)]
        zone(data, 'copper', 6, 22)
        zone(data, 'vendor', 6, 21)
        p, _, _ = plan(data)
        p.v.commands.clear()
        p.v.busy.clear()
        p.v.targets.clear()
        p.plan.budget = main.BudgetReserve(0, 0)
        p.arbiter = main.ActionArbiter(p.v, p.plan.budget)
        for actor, kind in [('1', 'WALL_SERVICE'), ('2', 'UPGRADE')]:
            job = main.RoleJob(actor, kind, None, 'START', 70, 261, 330)
            p.execute_job(job, main.empty_response())
            self.assertEqual(job.job_type, kind)
            self.assertIn(p.v.commands[actor]['action'], {'move', 'collect', 'sell'})

    def test_full_backpack_cannot_start_purchase_but_held_voucher_can_be_used(self):
        data = checkpoint(gold=250)
        worker = data['teamOur']['roles'][1]
        worker.update(backpack=['copper'] * 100, backPackCapability=100)
        p, _, _ = plan(data)
        self.assertFalse(p.can_service('2', p.world.roles['24'], 'WallUpgradeVoucher1', 250))
        worker['backpack'][-1] = 'WallUpgradeVoucher1'
        p, _, _ = plan(data)
        self.assertTrue(p.can_service('2', p.world.roles['24'], 'WallUpgradeVoucher1', 250))

    def test_checkpoint_values_match_original_logs(self):
        root = Path(__file__).resolve().parents[1] / 'log/Versus/round4'
        for game, rounds in [(11, [131]), (12, [131, 260, 330])]:
            rows = {}
            for line in next((root / f'game{game}').glob('ally*.log')).read_text(encoding='utf-8').splitlines():
                for marker in ('[trace_turn] ', '[shadow_turn] '):
                    if marker in line:
                        row = json.loads(line.split(marker, 1)[1])
                        rows[marker, row['round']] = row
            for r in rounds:
                fixture = checkpoint(game, r)
                trace = rows['[trace_turn] ', r]
                metrics = rows['[shadow_turn] ', r]['metrics']
                self.assertEqual(fixture['teamOur']['goldNum'], trace['gold'])
                self.assertEqual([x['health'] for x in fixture['teamOur']['roles'] if x['roleType'] == 'station'], metrics['station_hp'])
                self.assertEqual(sorted(x['health'] for x in fixture['teamOur']['roles'] if x['roleType'] in main.CHARACTERS),
                                 sorted(x['health'] for x in trace['roles'] if x['kind'] in main.CHARACTERS))
                self.assertEqual(sum(x['health'] for x in fixture['teamOur']['roles'] if x['roleType'] == 'wall'), sum(metrics['wall_hp']))

    def test_day4_holds_day3_policy_and_reports_authority(self):
        data = checkpoint(gold=250)
        data['roundNo'] = 391
        memory = main.GameMemory((7, 'challenger'), 1)
        world = main.World(data)
        p = main.StrategicPlanner(world, memory, memory.observe(world, 391), main.Rules(), authority=True)
        _, report = p.run(main.empty_response())
        self.assertEqual(report['strategy_mode'], 'defense')
        self.assertEqual(p.plan.weapon_level_target, (2, 2, 1))
        self.assertTrue(p.intended_response['roleCommandMap'])

    def test_station_gap_does_not_preempt_feasible_growth(self):
        data = checkpoint(round_no=330, gold=250)
        data['roundNo'] = 261
        p, _, report = plan(data)
        self.assertNotIn('STATION_GAP_FALLBACK', report['reasons'])
        # Controlled unreachable construction/upgrade geometry: station remains reachable.
        original = main.StrategicPlanner.can_service
        def services(planner, actor, building, name, funds):
            return original(planner, actor, building, name, funds) if name in {'Medicine', 'StationUpgradeVoucher1'} else False
        with patch.object(main.StrategicPlanner, 'can_service', services), \
                patch.object(main.StrategicPlanner, 'completion_trip', return_value=None):
            p, _, report = plan(data)
        self.assertIn('STATION_GAP_FALLBACK', report['reasons'])

    def test_partial_wall_target_keeps_largest_feasible_and_rule_cost(self):
        for feasible in (5, 3, 2, 1):
            data = checkpoint(11)
            data['roundNo'] = 1
            for r in data['teamOur']['roles']:
                if r['roleType'] == 'station':
                    r['health'] = 1500
            def estimate(planner, job, slot):
                return (100, 1) if job.job_type == 'BUILD_WALL' and planner.plan.execution_wall_target > feasible else (1, 1)
            with patch.object(main.StrategicPlanner, 'completion_trip', estimate):
                p, _, _ = plan(data)
            self.assertEqual((p.plan.benchmark_wall_target, p.plan.execution_wall_target), (8, feasible))
        data = defense_day(1)
        p, _, _ = plan(data)
        job = main.RoleJob('1', 'BUILD_WALL', None, 'START', 70, 1, 70)
        p.plan.execution_wall_target = 3
        one = p.completion_trip(job, (8, 21))
        p.rules = main.Rules(wall_stone_cost=2)
        two = p.completion_trip(job, (8, 21))
        self.assertEqual(two[0] - one[0], 3)

    def test_game11_r131_no_tall_weapon_and_station_emergency(self):
        p, _, report = plan(checkpoint(11))
        self.assertNotIn('WeaponUpgradeVoucher2', [c.get('name') for c in p.v.commands.values()])
        self.assertIn('STATION_EMERGENCY', report['reasons'])
        self.assertEqual(p.plan.budget.reserved_gold.get('station', 0) +
                         sum(100 for c in p.v.commands.values() if c.get('name') == 'StationUpgradeVoucher1'), 100)
        legacy = main.GameSession(origin=1, strategy_mode='legacy').handle(checkpoint(11))
        self.assertNotIn('WeaponUpgradeVoucher2', [c.get('name') for c in legacy['roleCommandMap'].values()])

    def test_game12_checkpoints_metrics_and_health(self):
        for r, current in [(131, 5845), (260, 4850), (330, 6755)]:
            p, _, report = plan(checkpoint(round_no=r))
            self.assertEqual(report['metrics']['wall_current_hp_total'], current)
            self.assertEqual(report['metrics']['wall_max_hp_total'], 8000)
            self.assertEqual(report['metrics']['wall_level_counts'], {1: 8})
            self.assertFalse(report['metrics']['controller_health_ready']['1'])
            if r == 330:
                self.assertEqual(p.plan.weapon_level_target, (2, 2, 1))
                self.assertIn('WALL_MAX_HP', report['readiness_unmet'])

    def test_hot_damaged_l1_upgrade_and_fixer_fallback(self):
        data = checkpoint(gold=250)
        p, _, _ = plan(data)
        hot = p.world.roles['24']
        self.assertEqual(p.wall_item(hot, '2'), 'WallUpgradeVoucher1')
        p.plan.budget = main.BudgetReserve(10, 10)
        self.assertEqual(p.wall_item(hot, '2'), 'WallFixer')
        hot['level'] = 3
        self.assertEqual(p.wall_item(hot, '2'), 'WallFixer')

    def test_breadth_target_selects_l1(self):
        data = checkpoint(round_no=330, gold=250)
        data['roundNo'] = 261
        p, _, _ = plan(data)
        p.v.commands.clear()
        p.v.busy.clear()
        p.plan.budget = main.BudgetReserve(250, 250)
        p.arbiter = main.ActionArbiter(p.v, p.plan.budget)
        job = main.RoleJob('1', 'UPGRADE', None, 'START', 60, 261, 330)
        p.execute_job(job, main.empty_response())
        self.assertEqual(main.level_of(p.world.roles[job.target]), 1)
        self.assertEqual(p.v.commands['1']['name'], 'WeaponUpgradeVoucher1')

    def test_medicine_single_purchase_and_use(self):
        data = checkpoint(gold=250)
        p, _, _ = plan(data)
        self.assertEqual(p.v.commands['1'], {'action': 'buy', 'name': 'Medicine', 'num': 1})
        data['teamOur']['roles'][0]['backpack'] = ['Medicine']
        p, _, _ = plan(data)
        self.assertEqual(p.v.commands['1'], {'action': 'use', 'name': 'Medicine'})

    def test_wall_voucher_purchase_observe_delivery_and_capacity_growth(self):
        data = checkpoint(gold=250)
        p, memory, _ = plan(data)
        self.assertEqual(p.v.commands['2'], {'action': 'buy', 'name': 'WallUpgradeVoucher1', 'num': 1})
        data['roundNo'] = 132
        data['teamOur']['goldNum'] = 220
        worker = next(r for r in data['teamOur']['roles'] if r['id'] == 2)
        worker.update(pos=dict(x=11, y=22), backpack=['WallUpgradeVoucher1'])
        # Recorded-observation style inputs: travel outcome is supplied, not simulated.
        p, memory, _ = shadow(data, memory)
        self.assertEqual(p.v.commands['2'], {'action': 'use', 'name': 'WallUpgradeVoucher1',
                                             'targetPos': [dict(x=12, y=22)]})
        data['roundNo'] = 133
        worker['backpack'] = []
        next(r for r in data['teamOur']['roles'] if r['id'] == 24).update(level=2, health=1500)
        _, _, report = shadow(data, memory)
        self.assertEqual(report['metrics']['wall_max_hp_total'], 8500)
        self.assertEqual(report['metrics']['wall_current_hp_total'], 5845 + 1110)

    def test_active_task_pioneer_and_channels_have_one_owner(self):
        data = checkpoint(gold=250)
        data['phaseTask'] = 'test-task'
        data['teamOur']['roles'][2]['health'] = 75
        calls = []
        def task_run(task, response):
            calls.append(1)
            task.v.memory.accepted_task = 'persisted-by-legacy-task'
            response['prompt'] = 'task prompt'
            response['executeCmd'] = 'echo task'
        session = main.GameSession(origin=1, strategy_mode='defense')
        with patch.object(main.TaskPlanner, 'run', task_run):
            response = session.handle(data)
        self.assertEqual(len(calls), 1)
        self.assertEqual(response['prompt'], 'task prompt')
        self.assertEqual(response['executeCmd'], 'echo task')
        self.assertEqual(session.memory.accepted_task, 'persisted-by-legacy-task')
        self.assertNotIn('3', response['roleCommandMap'])
        self.assertFalse(any(c.get('controllerId') == '3' for c in response['roleCommandMap'].values()))

    def test_default_shadow_equal_legacy_and_defense_explicit(self):
        data = checkpoint()
        self.assertEqual(main.DEFAULT_STRATEGY_MODE, 'shadow')
        self.assertEqual(main.GameSession(origin=1).handle(deepcopy(data)),
                         main.GameSession(origin=1, strategy_mode='legacy').handle(deepcopy(data)))
        main.GameSession(origin=1, strategy_mode='defense').handle(data)

    def test_task_diagnostics_no_association_across_gap(self):
        data = checkpoint()
        memory = main.GameMemory((7, 'challenger'), 1)
        memory.observe(main.World(data), 131)
        data['phaseTask'] = 'task'
        data['errors'] = [{'errorCode': 2}, {'errorCode': 1}]
        memory.observe(main.World(data), 132)
        self.assertEqual(memory.task_diagnostics['task_started'], 132)
        self.assertEqual(memory.task_diagnostics['task_error_codes'], [2, 1])
        data['phaseTask'] = ''
        memory.observe(main.World(data), 134)
        self.assertIsNone(memory.task_diagnostics['task_end'])
        self.assertIsNone(memory.task_diagnostics['gold_before'])

    def test_dusk_growth_separates_current_and_capacity(self):
        data = checkpoint()
        _, memory, _ = plan(data)
        data['roundNo'] = 200
        data['teamOur']['roles'][-1].update(level=2, health=1500)
        _, _, report = shadow(data, memory)
        growth = report['defense_growth']
        self.assertEqual(growth['wall_max_hp_start'], 8000)
        self.assertEqual(growth['wall_max_hp_end'], 8500)
        self.assertEqual(growth['wall_current_hp_start'], 5845)

    def test_deadline_rejects_purchase_without_debit(self):
        data = checkpoint(round_no=330, gold=250)
        p, _, _ = plan(data)
        before = p.plan.budget.staged_gold
        self.assertFalse(p.can_service('1', p.world.roles['24'], 'WallUpgradeVoucher1', 250))
        self.assertEqual(p.plan.budget.staged_gold, before)
