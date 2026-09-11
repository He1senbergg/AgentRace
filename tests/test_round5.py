"""V2.3 contracts; game17 checkpoints use controlled geometry, not a match simulator."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src import main3 as main
from src.agentrace.memory import CapitalGoal, BlockReason
from src.agentrace.model import ProductionPolicy
from src.agentrace.strategy import StrategicPlanner
from test_actions import zone
from test_round3 import defense_day
from test_shadow import shadow


def production(round_no=18, gold=80):
    data = defense_day(1)
    data['roundNo'] = round_no
    data['teamOur']['goldNum'] = gold
    for r in data['teamOur']['roles']:
        r['health'] = 1500 if r['roleType'] == 'station' else 220 if r['roleType'] == 'worker' else 200
        if r['roleType'] == 'rocket':
            r.update(level=1, health=1000)
    zone(data, 'vendor', 6, 21)
    zone(data, 'copper', 6, 23)
    data['vendorShopList'] = [dict(name='copper', price=5)]
    return data


def setup(data):
    memory = main.GameMemory((7, 'challenger'), 1)
    world = main.World(data)
    p = StrategicPlanner(world, memory, memory.observe(world, data['roundNo']), main.Rules())
    p.reconcile()
    return p


class Round5Tests(unittest.TestCase):
    def test_game17_source_timeline(self):
        path = next((Path(__file__).resolve().parents[1]/'log/Versus/round5/game17').glob('ally*.log'))
        rows = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            if '[shadow_turn] ' in line:
                row = json.loads(line.split('[shadow_turn] ', 1)[1])
                rows[row['round']] = row
        self.assertEqual(rows[18]['budget']['observed_gold'], 80)
        self.assertEqual(rows[70]['budget']['observed_gold'], 194)
        self.assertEqual([rows[r]['defense_target']['execution_wall_target'] for r in [1, 2, 5, 7]], [8, 6, 1, 0])
        self.assertEqual(rows[37]['jobs']['10010']['job_type'], 'RETURN')
        self.assertFalse(any(j['job_type'] == 'UPGRADE' for j in rows[37]['jobs'].values()))
        self.assertEqual(rows[70]['metrics']['weapon_levels'], [1, 1, 1])

    def test_wall_next_trip_not_global_batch_and_no_collapse(self):
        memory = main.GameMemory((7, 'challenger'), 1)
        for r in [1, 2, 5, 18]:
            p, memory, report = shadow(production(r, 0), memory)
            self.assertEqual((p.plan.benchmark_wall_target, p.plan.execution_wall_target), (8, 8))
            jobs = [j for j in p.plan.jobs.values() if j.job_type == 'BUILD_WALL']
            self.assertTrue(jobs)
            self.assertTrue(any(p.v.commands.get(j.owner, {}).get('action') in {'move', 'collect', 'build'} for j in jobs))
        job = jobs[0]
        first = p.completion_trip(job, p.plan.controllers[job.owner].safe_slot)
        p.plan.execution_wall_target = 100
        self.assertEqual(p.completion_trip(job, p.plan.controllers[job.owner].safe_slot), first)
        p.rules = main.Rules(wall_stone_cost=2)
        self.assertEqual(p.completion_trip(job, p.plan.controllers[job.owner].safe_slot)[0], first[0] + 1)

    def test_parallel_builders_reserve_distinct_persistent_slots(self):
        data = production(1, 100)
        # Pioneer owns an observed voucher; both workers are free to build.
        data['teamOur']['roles'][2]['backpack'] = ['WeaponUpgradeVoucher1']
        p, memory, _ = shadow(data, main.GameMemory((7, 'challenger'), 1))
        builders = {a: j.target for a, j in p.plan.jobs.items() if j.job_type == 'BUILD_WALL'}
        self.assertEqual(len(builders), 2)
        self.assertEqual(len(set(builders.values())), 2)
        data['roundNo'] = 2
        p, _, _ = shadow(data, memory)
        self.assertEqual({a: j.target for a, j in p.plan.jobs.items() if j.job_type == 'BUILD_WALL'}, builders)

    def test_funded_goal_releases_stale_daytime_return(self):
        data = production(37, 144)
        memory = main.GameMemory((7, 'challenger'), 1)
        for actor in ['1', '2', '3']:
            memory.strategic.plan.jobs[actor] = main.RoleJob(actor, 'RETURN', None, 'HOLD', 100, 28, 130)
        p, _, _ = shadow(data, memory)
        goal = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
        self.assertIsNotNone(goal.assigned_actor)
        self.assertNotEqual(p.plan.jobs[goal.assigned_actor].job_type, 'RETURN')
        self.assertIn(p.v.commands[goal.assigned_actor]['action'], {'buy', 'move'})

    def test_forced_liquidation_and_observed_purchase_use_verify(self):
        data = production()
        worker = data['teamOur']['roles'][1]
        worker['backpack'] = ['copper'] * 4
        memory = main.GameMemory((7, 'challenger'), 1)
        p, memory, report = shadow(data, memory)
        self.assertEqual(p.v.commands['2'], {'action': 'sell', 'name': 'copper', 'num': 4})
        self.assertEqual(p.plan.budget.staged_gold, 80)  # sale is not spendable in this turn
        goal_id = next(g.goal_id for g in p.plan.capital_goals.values() if g.assigned_actor == '2')
        self.assertEqual(p.plan.capital_goals[goal_id].state, 'LIQUIDATE')
        # Failed sale: identical bag and cash, never start another mining trip.
        data['roundNo'] = 19
        p, memory, _ = shadow(data, memory)
        self.assertEqual(p.v.commands['2']['action'], 'sell')
        data['roundNo'] = 20
        data['teamOur']['goldNum'] = 100
        worker['backpack'] = []
        p, memory, _ = shadow(data, memory)
        self.assertEqual(p.v.commands['2'], {'action': 'buy', 'name': 'WeaponUpgradeVoucher1', 'num': 1})
        data['roundNo'] = 21
        worker['backpack'] = ['WeaponUpgradeVoucher1']
        data['teamOur']['goldNum'] = 0
        worker['pos'] = dict(x=8, y=21)
        p, memory, report = shadow(data, memory)
        self.assertEqual(p.v.commands['2']['action'], 'use')
        self.assertEqual(p.plan.capital_goals[goal_id].state, 'VERIFY')
        row = next(row for row in report['capital_deployment'] if row['goal_id'] == goal_id)
        self.assertFalse(row['executable_now'])
        self.assertEqual(row['block_reasons'], ['VERIFICATION_PENDING'])
        data['roundNo'] = 22
        worker['backpack'] = []
        next(r for r in data['teamOur']['roles'] if r['id'] == 10).update(level=2, health=1500)
        p, memory, report = shadow(data, memory)
        self.assertEqual(p.plan.capital_goals[goal_id].state, 'DONE')
        row = next(row for row in report['capital_deployment'] if row['goal_id'] == goal_id)
        self.assertIsNone(row['accepted_action'])
        self.assertFalse(row['executable_now'])

    def test_diagnostics_separate_cash_deadline_and_job_blockers(self):
        p = setup(production())
        w = p.world.roles['10']
        p.plan.jobs['2'] = main.RoleJob('2', 'UPGRADE', '10', 'START', 60, 18, 70)
        row = p.capital_status('g', 'UPGRADE', w, 'WeaponUpgradeVoucher1', '2', 'upgrade', {'UPGRADE'})
        self.assertEqual(row['block_reason'], 'FUNDING_GAP')
        self.assertTrue(row['route_feasible'])
        self.assertTrue(row['deadline_feasible'])
        p.plan.jobs['2'].job_type = 'RETURN'
        row = p.capital_status('g', 'UPGRADE', w, 'WeaponUpgradeVoucher1', '2', 'upgrade', {'UPGRADE'})
        self.assertEqual(row['block_reason'], 'WRONG_JOB_STATE')
        late = setup(production(70, 194))
        late.plan.jobs['2'] = main.RoleJob('2', 'UPGRADE', '10', 'START', 60, 70, 70)
        row = late.capital_status('g', 'UPGRADE', late.world.roles['10'], 'WeaponUpgradeVoucher1', '2', 'upgrade', {'UPGRADE'})
        self.assertEqual(row['block_reason'], 'DEADLINE')
        self.assertEqual(row['funding_gap'], 0)
        self.assertIn(row['block_reason'], {r.value for r in BlockReason})

    def test_pioneer_task_lock_feasible_task_and_logistics_permissions(self):
        data = production(1, 100)
        data['phaseTask'] = 'active'
        p = setup(data)
        self.assertEqual(p.plan.jobs['3'].job_type, 'TASK_LOCK')
        data['phaseTask'] = ''
        data['teamOur']['playerTasks'] = [dict(taskPosition=dict(x=6, y=24), isValid=True, coldDownRounds=0, timeoutRounds=3)]
        zone(data, 'challengerTaskPoint1', 6, 24)
        p = setup(data)
        self.assertEqual(p.plan.jobs['3'].job_type, 'TASK')
        data['teamOur']['playerTasks'] = []
        data['teamOur']['roles'][2]['backpack'] = ['WeaponUpgradeVoucher1']
        p = setup(data)
        job = p.plan.jobs['3']
        self.assertEqual(job.job_type, 'LOGISTICS')
        self.assertFalse(p.propose(job, {'action': 'collect', 'targetPos': [dict(x=6, y=24)]}))
        self.assertFalse(p.propose(job, {'action': 'build', 'name': 'wall', 'targetPos': [dict(x=6, y=24)]}))
        p.execute_job(job, main.empty_response())
        self.assertIn(p.v.commands['3']['action'], {'move', 'use'})

    def test_growth_floors_and_observed_pressure(self):
        policy = ProductionPolicy()
        self.assertEqual([policy.capacity_target(d, {}) for d in [1, 2, 3, 4]], [8000, 12000, 15000, 15000])
        quiet = dict(previous_capacity=16000)
        damage = dict(quiet, wall_hp_loss=4000, missing_wall_ids=['w'], station_hp_loss=100, missing_controller_ids=['c'])
        self.assertEqual(policy.capacity_target(4, quiet), 16000)
        self.assertEqual(policy.capacity_target(4, damage), 20500)
        p, memory, _ = shadow(production(331), main.GameMemory((7, 'challenger'), 1))
        data = production(332)
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles'] if r['id'] != 2]
        p, memory, _ = shadow(data, memory)
        data['roundNo'] = 391
        p, _, report = shadow(data, memory)
        self.assertEqual(report['growth_basis']['missing_controller_ids'], ['2'])

    def test_missing_end_of_night_stays_incomplete_after_dawn(self):
        memory = main.GameMemory((7, 'challenger'), 1)
        for r in [71, 120, 131, 132]:
            p, memory, _ = shadow(production(r), memory)
        self.assertFalse(p.state.growth_basis['complete'])

    def test_low_health_pioneer_heals_before_new_task_but_active_task_is_locked(self):
        data = production(131, 100)
        data['teamOur']['roles'][2]['health'] = 50
        data['weaponShopList'].append(dict(name='Medicine', price=10))
        data['teamOur']['playerTasks'] = [dict(taskPosition=dict(x=6, y=24), isValid=True, coldDownRounds=0, timeoutRounds=3)]
        zone(data, 'challengerTaskPoint1', 6, 24)
        p = setup(data)
        self.assertTrue(any(g.goal_type == 'HEAL' and g.assigned_actor == '3' for g in p.plan.capital_goals.values()))
        self.assertNotEqual(p.plan.jobs['3'].job_type, 'TASK')
        data['phaseTask'] = 'already active'
        p = setup(data)
        self.assertEqual(p.plan.jobs['3'].job_type, 'TASK_LOCK')

    def test_full_inventory_cash_route_includes_vendor_before_shop(self):
        data = production(50, 100)
        data['teamOur']['roles'][1]['backpack'] = ['copper'] * 100
        data['mapInfo']['zones'] = [z for z in data['mapInfo']['zones'] if z['neutralType'] != 'vendor']
        zone(data, 'vendor', 35, 25)
        p = setup(data)
        p.plan.jobs['2'] = main.RoleJob('2', 'UPGRADE', '10', 'START', 60, 50, 70)
        row = p.capital_status('g', 'UPGRADE', p.world.roles['10'], 'WeaponUpgradeVoucher1', '2', 'upgrade', {'UPGRADE'})
        self.assertTrue(row['route_feasible'])
        self.assertFalse(row['deadline_feasible'])
        self.assertEqual(row['block_reason'], 'DEADLINE')

    def test_force_bypasses_only_goal_liquidation_roi_and_does_not_mine(self):
        from src.agentrace.economy import EconomyPlanner
        data = production(18, 80)
        data['teamOur']['roles'][1]['backpack'] = ['copper'] * 4
        data['mapInfo']['zones'] = [z for z in data['mapInfo']['zones'] if z['neutralType'] != 'vendor']
        zone(data, 'vendor', 3, 21)
        p = setup(data)
        scratch = main.ActionValidator(p.world, p.memory, p.rules)
        self.assertFalse(EconomyPlanner(scratch).cash_in(p.world.characters['2']))
        goal = next(g for g in p.plan.capital_goals.values() if g.assigned_actor == '2')
        p.execute_job(p.plan.jobs['2'], main.empty_response())
        self.assertEqual(goal.state, 'LIQUIDATE')
        self.assertEqual(p.v.commands['2']['action'], 'move')
        self.assertLess(p.v.commands['2']['targetPos'][0]['x'], 7)

    def test_use_without_observed_level_change_never_claims_done_or_rebuys(self):
        p = setup(production(18, 200))
        goal = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
        goal.last_action, goal.last_action_round, goal.state = 'use', 17, 'VERIFY'
        p.execute_job(p.plan.jobs[goal.assigned_actor], main.empty_response())
        self.assertEqual(goal.state, 'VERIFY')
        self.assertEqual(goal.block_reason, 'VERIFICATION_PENDING')
        self.assertNotIn(goal.assigned_actor, p.v.commands)

    def test_capital_actor_death_reassigns_goal_without_false_completion(self):
        data = production(18, 100)
        p, memory, _ = shadow(data, main.GameMemory((7, 'challenger'), 1))
        goal = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
        actor = goal.assigned_actor
        data['roundNo'] = 19
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles'] if str(r['id']) != actor]
        p, _, _ = shadow(data, memory)
        new = p.plan.capital_goals[goal.goal_id]
        self.assertNotEqual(new.assigned_actor, actor)
        self.assertNotEqual(new.state, 'DONE')

    def test_other_weapon_upgrade_satisfies_breadth_goal_without_extra_purchase(self):
        data = production(18, 100)
        p, memory, _ = shadow(data, main.GameMemory((7, 'challenger'), 1))
        goal = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
        self.assertEqual(goal.target, '10')
        data['roundNo'] = 19
        next(r for r in data['teamOur']['roles'] if r['id'] == 11).update(level=2, health=1500)
        p, _, report = shadow(data, memory)
        self.assertEqual(p.plan.capital_goals[goal.goal_id].block_reason, 'SUPERSEDED')
        self.assertNotEqual(p.plan.capital_goals[goal.goal_id].state, 'DONE')
        self.assertFalse(any(c.get('name') == 'WeaponUpgradeVoucher1' for c in p.v.commands.values()))

    def test_complete_night_captures_final_damage_and_does_not_change_on_day2(self):
        memory = main.GameMemory((7, 'challenger'), 1)
        for r in range(71, 131):
            _, memory, _ = shadow(production(r), memory)
        data = production(131)
        next(r for r in data['teamOur']['roles'] if r['roleType'] == 'station')['health'] = 1400
        p, memory, _ = shadow(data, memory)
        self.assertTrue(p.state.growth_basis['complete'])
        self.assertEqual(p.state.growth_basis['station_hp_loss'], 100)
        data['roundNo'] = 132
        p, _, _ = shadow(data, memory)
        self.assertTrue(p.state.growth_basis['complete'])


if __name__ == '__main__':
    unittest.main()
