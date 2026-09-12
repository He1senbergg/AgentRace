"""Sonnet E2–E5 regression contracts; synthetic geometry is not a battle replay."""
from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from src import main3 as main
from src.agentrace.defense import ShadowDefensePlanner
from src.agentrace.memory import CapitalGoal
from test_actions import role, state, validator, zone
from test_defense import robot
from test_round5 import production, setup


class SonnetV24Tests(unittest.TestCase):
    def test_front_wall_priority_mirrors_and_keeps_valid_reservation(self):
        for anchor, worker, front in [((9, 22), (7, 22), (12, 22)),
                                      ((30, 10), (33, 10), (28, 9))]:
            with self.subTest(anchor=anchor):
                data = state(role(1, 'worker', *worker), role(9, 'station', *anchor, level=1))
                data['roundNo'] = 1
                p = setup(data)
                p.plan.jobs = {}
                p.plan.controllers = {}
                job = main.RoleJob('1', 'BUILD_WALL', None, 'START', 70, 1, 70)
                self.assertEqual(p.wall_slot(job), front)
                # A legal persistent target is retained even when another slot ranks first.
                old = p.layout.wall_slots[-1]
                job.target = old
                self.assertEqual(p.wall_slot(job), old)
                p.world.static_occupied.add(old)
                self.assertEqual(p.wall_slot(job), front)

    def test_wall_reservations_controller_slots_and_unreachable_candidates(self):
        p = setup(production(1, 0))
        p.plan.jobs = {}
        p.plan.controllers = {}
        first, second, third = p.layout.wall_slots[:3]
        job = main.RoleJob('1', 'BUILD_WALL', None, 'START', 70, 1, 70)
        p.plan.jobs['2'] = main.RoleJob('2', 'BUILD_WALL', first, 'START', 70, 1, 70)
        p.plan.controllers['3'] = main.ControllerAssignment('3', second)
        self.assertEqual(p.wall_slot(job), third)
        p.layout = replace(p.layout, wall_slots=())
        self.assertIsNone(p.wall_slot(job))
        p.layout = replace(p.layout, wall_slots=(third,))
        with patch.object(main.World, 'path', return_value=None):
            self.assertIsNone(p.wall_slot(job))

    def test_two_workers_build_second_and_third_weapon_in_one_turn(self):
        for names, expected in [(main.Rules().weapon_build_names, ['rocket', 'railgun']),
                                ((('R', 'rocket'), ('E', 'railgun')), ['R', 'E']),
                                ((('R', 'rocket'),), ['R', 'R'])]:
            with self.subTest(names=names):
                data = production(1, 50)
                data['teamOur']['roles'] = [r for r in data['teamOur']['roles']
                                           if r['roleType'] != 'rocket' or r['id'] == 10]
                data['teamOur']['roles'][0]['pos'] = dict(x=7, y=21)
                data['teamOur']['roles'][1]['pos'] = dict(x=7, y=23)
                world = main.World(data)
                memory = main.GameMemory((7, 'challenger'), 1)
                p = main.StrategicPlanner(world, memory, memory.observe(world, 1),
                                          main.Rules(weapon_build_names=names), authority=True)
                p.reconcile()
                for actor in ('1', '2'):
                    p.execute_job(p.plan.jobs[actor], main.empty_response())
                self.assertEqual([p.v.commands[a]['name'] for a in ('1', '2')], expected)
                self.assertTrue(all(c['action'] == 'build' for c in p.v.commands.values()))
                self.assertEqual(p.v.weapon_count, 3)
                self.assertEqual(p.plan.budget.staged_gold, 0)

    def test_defense_session_builds_mixed_opening_and_caches_each_turn(self):
        data = production(1, 75)
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles'] if r['roleType'] != 'rocket']
        session = main.GameSession(origin=1, strategy_mode='defense')
        built = []
        for turn in range(1, 21):
            data['roundNo'] = turn
            response = session.handle(data)
            self.assertEqual(session.handle(deepcopy(data)), response)
            feedback = {}
            for actor, command in response['roleCommandMap'].items():
                character = next(r for r in data['teamOur']['roles'] if str(r['id']) == actor)
                if command['action'] == 'move':
                    character['pos'] = command['targetPos'][0]
                elif command['action'] == 'build':
                    name = command['name']
                    self.assertIn(name, ('rocket', 'railgun'))
                    built.append(name)
                    cell = command['targetPos'][0]
                    weapon = role(100 + len(built), name, cell['x'], cell['y'], level=1)
                    weapon['health'] = 1000
                    data['teamOur']['roles'].append(weapon)
                    data['teamOur']['goldNum'] -= 25
                feedback[actor] = True
            data['lastRoundRoleActionResults'] = feedback
            if len(built) == 3:
                break
        self.assertEqual(built, ['rocket', 'rocket', 'railgun'])
        self.assertEqual(data['teamOur']['goldNum'], 0)

    def test_pioneer_owner_requires_funded_gap_or_held_item(self):
        for gold, bag, allowed in [(76, [], False), (76, ['copper'] * 4, False),
                                   (75, ['copper'] * 5, True), (100, [], True),
                                   (0, ['WeaponUpgradeVoucher1'], True)]:
            with self.subTest(gold=gold, bag=bag):
                data = production(18, gold)
                data['teamOur']['roles'][2]['backpack'] = bag
                p = setup(data)
                goal = CapitalGoal('test', 'UPGRADE', '10', 'WeaponUpgradeVoucher1', 'upgrade', 2)
                goal.assigned_actor = '3'  # Exercise reassignment of a stale pioneer owner.
                p.plan.capital_goals = {'test': goal}
                p.plan.jobs = {}
                with patch.object(p, 'purchase_goals', return_value=[goal]):
                    p.schedule_production(70)
                self.assertEqual(goal.assigned_actor == '3', allowed)
                self.assertIsNotNone(goal.assigned_actor)
                owner = goal.assigned_actor
                p.execute_job(p.plan.jobs[owner], main.empty_response())
                self.assertIn(owner, p.v.commands)
                if allowed:
                    self.assertIn(p.v.commands[owner]['action'], ('move', 'sell', 'buy', 'use'))
                if not allowed:
                    self.assertEqual(p.world.characters[owner]['roleType'], 'worker')
                    self.assertEqual(goal.state, 'FUNDING')

    def test_unfunded_pioneer_only_has_no_capital_owner(self):
        data = production(18, 0)
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles'] if r['roleType'] != 'worker']
        p = setup(data)
        goals = [g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE']
        self.assertTrue(goals)
        self.assertTrue(all(g.assigned_actor is None for g in goals))
        self.assertEqual(p.plan.jobs['3'].job_type, 'LOGISTICS')

    def test_growth_scorer_prioritizes_base_threat_without_mutating_prediction(self):
        data = state(role(1, 'worker', 14, 17), role(9, 'station', 10, 10, level=1),
                     role(10, 'railgun', 10, 13, level=1),
                     robot=[robot(50, 10, 11), robot(51, 14, 16)])
        for growth, target in [(False, (14, 16)), (True, (10, 11))]:
            d = ShadowDefensePlanner(validator(data, main.Phase(1, 71)), growth_mode=growth)
            before = dict(d.remaining)
            selected, after, score = d.attack_plan(d.weapons[0])
            self.assertEqual(selected, [target])
            self.assertEqual(d.remaining, before)
            self.assertEqual(sum(before.values()) - sum(after.values()), 10)
            self.assertGreater(score, 0)

    def test_finishing_bonus_at_exact_damage_boundary_and_no_base(self):
        data = state(role(10, 'railgun', 10, 10, level=1),
                     robot=[robot(50, 10, 12, 10), robot(51, 12, 10, 11)])
        d = ShadowDefensePlanner(validator(data, main.Phase(1, 71)), growth_mode=True)
        selected, after, score = d.attack_plan(d.weapons[0])
        self.assertEqual(selected, [(10, 12)])
        self.assertEqual(after, {'50': 0, '51': 11})
        self.assertEqual(score, 20)
        d.remaining['50'] = 0
        self.assertEqual(d.attack_plan(d.weapons[0])[0], [(12, 10)])
        d.remaining['51'] = 0
        self.assertEqual(d.attack_plan(d.weapons[0])[0], [])

    def test_railgun_can_fire_while_rockets_cool_down(self):
        data = production(71, 0)
        weapons = [r for r in data['teamOur']['roles'] if r['roleType'] == 'rocket']
        for r in weapons:
            r['cooldown'] = 3
        weapons[-1].update(roleType='railgun', cooldown=0)
        data['robot'] = [robot(50, 10, 23)]
        response = main.GameSession(origin=1, strategy_mode='defense').handle(data)
        attacks = {a: c for a, c in response['roleCommandMap'].items() if c['action'] == 'attack'}
        self.assertEqual(set(attacks), {str(weapons[-1]['id'])})
        self.assertEqual(len(attacks[str(weapons[-1]['id'])]['targetPos']), 1)

    def test_opening_benchmark_tracks_new_weapon_composition(self):
        data = production(71, 0)
        layout = main.CanonicalLayout.from_world(main.World(data))
        for i, cell in enumerate(layout.wall_slots[:8]):
            data['teamOur']['roles'].append(dict(role(30+i, 'wall', *cell, level=1), health=1000))
        data['teamOur']['roles'][4].update(level=2, health=1500)
        for mixed in (False, True):
            if mixed:
                data['teamOur']['roles'][6]['roleType'] = 'railgun'
            p = setup(data)
            _, report = p.run(main.empty_response())
            self.assertEqual(report['metrics']['day1_benchmark_met'], mixed)
            self.assertEqual(report['scope'], 'v24_e2_e5_experiments')

    def test_helper_growth_cap_above_eight_and_legacy_gate(self):
        data = production(1, 0)
        for i, cell in enumerate([(11, 19), (12, 19), (12, 20), (12, 21),
                                  (12, 22), (12, 23), (12, 24), (11, 24)]):
            data['teamOur']['roles'].append(role(30+i, 'wall', *cell, level=1))
        data['teamOur']['roles'][0]['pos'] = dict(x=13, y=22)
        self.assertFalse(main.DefensePlanner(validator(data)).fortify())
        d = main.DefensePlanner(validator(data), growth_mode=True)
        self.assertTrue(d.fortify())
        self.assertIn(d.v.commands['1']['action'], ('move', 'collect'))
        d.v.wall_count = 20
        self.assertFalse(d.fortify())

    def test_capacity_override_reaches_shadow_helper_and_changes_wall_service(self):
        data = production(261, 100)
        data['weaponShopList'] = [item for item in data['weaponShopList']
                                 if item['name'] != 'WeaponUpgradeVoucher1']
        # The existing helpers are opt-in; production normally handles wall services itself.
        data['teamOur']['roles'].append(role(30, 'wall', 8, 20, level=1))
        low = ShadowDefensePlanner(validator(data, main.Phase(3, 1)), capacity_target=lambda day: 0,
                                   growth_mode=True)
        high = ShadowDefensePlanner(validator(data, main.Phase(3, 1)), capacity_target=lambda day: 15000,
                                    growth_mode=True)
        low.maintain()
        high.maintain()
        self.assertEqual(next(c['name'] for c in low.v.commands.values() if c['action'] == 'buy'), 'WallFixer')
        self.assertEqual(next(c['name'] for c in high.v.commands.values() if c['action'] == 'buy'), 'WallUpgradeVoucher1')
