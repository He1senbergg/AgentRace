"""Gate1 shadow isolation and resource contracts; no simulated combat claims."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from src import main3 as main
from src.agentrace import strategy
from src.agentrace import task_news
from src.agentrace import session as session_module
from test_actions import role, state, target, validator, zone


def opening():
    data = state(role(1, 'worker', 8, 21), role(2, 'worker', 11, 23),
                 role(3, 'pioneer', 7, 23), role(9, 'station', 9, 22, level=1),
                 weaponShopList=[dict(name='WeaponUpgradeVoucher1', price=100)])
    zone(data, 'stone', 14, 23)
    return data


def shadow(data, memory=None, rules=None):
    memory = memory or main.GameMemory((7, 'challenger'), 0)
    world = main.World(data)
    delta = memory.observe(world, data['roundNo'])
    planner = main.StrategicPlanner(world, memory, delta, rules or main.Rules())
    strategic, report = planner.run(main.empty_response())
    memory.strategic = strategic
    return planner, memory, report


class ShadowTests(unittest.TestCase):
    def test_attack_reserves_weapon_and_controller_atomically(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=1),
                     role(3, 'rocket', 9, 11, level=1))
        v = validator(data, main.Phase(1, 71))
        budget = main.BudgetReserve(75, 75)
        arbiter = main.ActionArbiter(v, budget)
        command = target('attack', 11, 10, controllerId='1')
        auth = main.JobAuthorization(frozenset({'1', '2', '3'}), frozenset({'attack', 'move'}), 'optional')
        self.assertFalse(arbiter.accept(main.ActionProposal('2', command, frozenset({'2'})), auth))
        self.assertFalse(v.busy)
        self.assertTrue(arbiter.accept(main.ActionProposal('2', command, frozenset({'1', '2'})), auth))
        self.assertEqual(v.busy, {'1', '2'})
        self.assertFalse(arbiter.accept(main.ActionProposal('3', command, frozenset({'1', '3'})), auth))
        self.assertFalse(arbiter.accept(main.ActionProposal('1', target('move', 8, 10), frozenset({'1'})), auth))

    def test_staged_budget_rejection_and_next_observation_reconciliation(self):
        data = state(role(1, 'worker', 9, 11), role(2, 'worker', 12, 11),
                     role(9, 'station', 10, 10, level=1))
        v = validator(data)
        budget = main.BudgetReserve(75, 75, {'build': 25, 'upgrade': 50})
        arbiter = main.ActionArbiter(v, budget)
        auth = main.JobAuthorization(frozenset({'1', '2'}), frozenset({'build'}), 'build')
        self.assertTrue(arbiter.accept(main.ActionProposal('1', target('build', 9, 10, name='rocket'), frozenset({'1'})), auth))
        self.assertEqual((budget.staged_gold, budget.committed_gold), (50, 25))
        self.assertFalse(arbiter.accept(main.ActionProposal('2', target('build', 12, 10, name='rocket'), frozenset({'2'})), auth))
        self.assertEqual((budget.staged_gold, v.gold, v.busy), (50, 50, {'1'}))
        p, memory, _ = shadow(opening())
        self.assertEqual(p.plan.budget.reserved_gold.get('upgrade'), 0)
        data = opening()
        data['roundNo'] = 1
        data['teamOur']['goldNum'] = 12
        p, _, _ = shadow(data, memory)
        self.assertEqual(p.plan.budget.observed_gold, 12)
        self.assertLessEqual(p.plan.budget.staged_gold, 12)

    def test_no_intended_action_feedback_or_gap_association(self):
        data = opening()
        p, memory, _ = shadow(data)
        self.assertTrue(p.v.commands)
        self.assertFalse(memory.previous_actions)
        data['roundNo'] = 2
        data['lastRoundRoleActionResults'] = {'1': False}
        p, memory, report = shadow(data, memory)
        self.assertFalse(memory.feedback['associated'])
        self.assertEqual(memory.feedback['actions'], {})
        self.assertIsNone(report['metrics']['associated_failures'])
        self.assertIn('observation_gap', report['reasons'])

    def test_layout_mirror_and_transient_slot_is_not_static(self):
        data = opening()
        data['teamOur']['roles'].append(role(88, 'worker', 9, 20))
        a = main.CanonicalLayout.from_world(main.World(data))
        self.assertEqual(a.weapon_slots[0], (9, 20))
        self.assertIn((9, 20), a.transient_occupancy)
        self.assertNotIn((9, 20), a.static_blockers)
        other = state(role(9, 'station', 30, 10, level=1))
        b = main.CanonicalLayout.from_world(main.World(other))
        self.assertEqual(b.weapon_slots[:3], tuple((40-x, 31-y) for x, y in a.weapon_slots[:3]))
        zone(data, 'stone', 9, 20)
        self.assertNotIn((9, 20), main.CanonicalLayout.from_world(main.World(data)).weapon_slots)

    def test_wall_job_persists_and_stone_cost_scales(self):
        data = opening()
        for i, p in enumerate(((9, 20), (8, 22), (8, 23)), 20):
            data['teamOur']['roles'].append(role(i, 'rocket', *p, level=1))
        worker = data['teamOur']['roles'][0]
        worker['pos'] = dict(x=13, y=23)
        worker['backpack'] = ['stone'] * 8
        p, memory, _ = shadow(data, rules=main.Rules(2))
        self.assertEqual(p.plan.jobs['1'].job_type, 'BUILD_WALL')
        self.assertIn(p.v.commands['1']['action'], {'move', 'build'})
        created = p.plan.jobs['1'].created_round
        data['roundNo'] = 1
        zone(data, 'copper', 13, 24)
        p, _, _ = shadow(data, memory, main.Rules(2))
        self.assertEqual(p.plan.jobs['1'].job_type, 'BUILD_WALL')
        self.assertEqual(p.plan.jobs['1'].created_round, created)
        self.assertIn(p.v.commands['1']['action'], {'move', 'build'})

    def test_prenight_depends_on_path_not_fixed_round(self):
        data = state(role(1, 'worker', 0, 0), role(2, 'rocket', 30, 20, level=1),
                     role(9, 'station', 30, 22, level=1))
        data['roundNo'] = 40
        p, _, _ = shadow(data)
        self.assertEqual(p.plan.mode, 'PRE_NIGHT')
        self.assertEqual(p.plan.jobs['1'].job_type, 'RETURN')
        data['teamOur']['roles'][0]['pos'] = dict(x=29, y=20)
        p, _, _ = shadow(data)
        self.assertNotEqual(p.plan.jobs['1'].job_type, 'RETURN')

    def test_cooldown_keeps_controller_and_prevents_economy(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=1, cooldown=3),
                     role(9, 'station', 10, 12, level=1))
        data['roundNo'] = 71
        p, memory, _ = shadow(data)
        assignment = p.plan.controllers['1']
        data['roundNo'] += 1
        data['teamOur']['roles'][1]['cooldown'] = 2
        p, _, _ = shadow(data, memory)
        self.assertEqual(p.plan.controllers['1'], assignment)
        self.assertEqual(p.plan.jobs['1'].job_type, 'CONTROL')
        self.assertNotIn(p.v.commands.get('1', {}).get('action'), {'collect', 'buy', 'sell'})

    def test_shadow_response_identity_repeat_and_error_isolation(self):
        data = opening()
        legacy = main.GameSession(strategy_mode='legacy')
        session = main.GameSession(strategy_mode='shadow')
        with self.assertLogs(main.LOG, level='INFO') as logs:
            actual = session.handle(data)
            self.assertEqual(actual, legacy.handle(data))
            self.assertEqual(session.handle(data), actual)
        rows = [json.loads(s.split('[shadow_turn] ', 1)[1]) for s in logs.output if '[shadow_turn]' in s]
        self.assertEqual(len(rows), 1)
        self.assertIn('intended', rows[0])
        self.assertIn('divergence', rows[0])
        self.assertNotIn('error', rows[0])
        old = deepcopy(session.memory.strategic)
        data['roundNo'] = 1
        with patch.object(strategy.StrategicPlanner, 'run', side_effect=RuntimeError('secret')):
            with self.assertLogs(main.LOG, level='INFO') as logs:
                self.assertEqual(session.handle(data), legacy.handle(data))
        self.assertEqual(session.memory.strategic, old)
        self.assertNotIn('secret', '\n'.join(logs.output))

    def test_no_v2_authority_option(self):
        with self.assertRaises(ValueError):
            main.GameSession(strategy_mode='v2')

    def test_indexed_rocket_estimate_matches_legacy_with_overlapping_robots(self):
        data = opening()
        data['robot'] = [role(100+i, 'smallRobot', i % 5, (i // 5) % 5) for i in range(60)]
        v = validator(data)
        old, new = main.DefensePlanner(v), main.ShadowDefensePlanner(v)
        for key in old.remaining:
            old.remaining[key] = new.remaining[key] = int(key) % 23
        weapon = dict(roleType='rocket', cell=(0, 0), level=1)
        for x in range(6):
            for y in range(6):
                self.assertEqual(new.damage(weapon, (x, y)), old.damage(weapon, (x, y)))

    def test_economy_does_not_clear_task_intended_channels(self):
        data = opening()
        p, _, _ = shadow(data)
        p.plan.jobs = {'3': main.RoleJob('3', 'TASK', None, 'START', 50, 0, 69),
                       '2': main.RoleJob('2', 'ECONOMY', None, 'START', 50, 0, 69)}
        response = main.empty_response()
        def task(_self, result):
            result['prompt'] = 'private task intent'
        with patch.object(task_news.TaskPlanner, 'run', task):
            p.execute_job(p.plan.jobs['3'], response)
            p.execute_job(p.plan.jobs['2'], response)
        self.assertEqual(response['prompt'], 'private task intent')

    def test_dead_weapon_invalidates_old_return_job(self):
        data = opening()
        p, memory, _ = shadow(data)
        memory.strategic.plan.jobs['1'] = main.RoleJob('1', 'RETURN', 'missing', 'TRAVEL', 100, 0, 129)
        data['roundNo'] = 1
        p, _, _ = shadow(data, memory)
        self.assertNotEqual(p.plan.jobs['1'].job_type, 'RETURN')

    def test_impossible_next_wall_pauses_before_early_return(self):
        data = opening()
        for i, cell in enumerate(((9, 20), (8, 22), (8, 23)), 20):
            data['teamOur']['roles'].append(role(i, 'rocket', *cell, level=1))
        p, memory, _ = shadow(data)
        wall_owner = next(a for a, j in p.plan.jobs.items() if j.job_type == 'BUILD_WALL')
        data['roundNo'] = 1
        def estimates(planner, job, slot):
            if job.job_type == 'BUILD_WALL':
                return (100, 1) if planner.plan.execution_wall_target > 2 else (5, 1)
            return (1, 1)
        with patch.object(strategy.StrategicPlanner, 'completion_trip', estimates):
            p, _, report = shadow(data, memory)
        self.assertEqual(p.plan.execution_wall_target, 8)
        self.assertEqual(p.plan.jobs[wall_owner].job_type, 'BUILD_WALL')
        self.assertIn('DEADLINE_INFEASIBLE', report['reasons'])

    def test_observation_replay_response_identity_across_boundaries(self):
        data = opening()
        legacy, session = main.GameSession(strategy_mode='legacy'), main.GameSession(strategy_mode='shadow')
        with patch.object(session_module.LOG, 'info') as log:
            for r in (0, 1, 2, 59, 69, 70, 71, 129, 130, 259, 260):
                data['roundNo'] = r
                self.assertEqual(session.handle(deepcopy(data)), legacy.handle(deepcopy(data)))
                for name in ('feedback', 'task', 'previous_actions', 'llm_calls_today', 'summon_attempts'):
                    self.assertEqual(getattr(session.memory, name), getattr(legacy.memory, name))
            reports = [json.loads(c.args[1]) for c in log.call_args_list if c.args[0] == '[shadow_turn] %s']
        self.assertEqual(len(reports), 11)
        self.assertTrue(all('error' not in r for r in reports))


if __name__ == '__main__':
    unittest.main()
