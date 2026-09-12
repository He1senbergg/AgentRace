"""Economic liveness regressions; settlement below does not simulate combat."""
from collections import Counter
from copy import deepcopy
import unittest

from src import main3 as main
from test_actions import role, zone
from test_round5 import production, setup


def isolated_wall(data):
    # All structures occupy the base's legal construction rings. Minerals only
    # block exterior cells, as the specification forbids spawning them in a ring.
    data['teamOur']['roles'].extend([
        dict(role(88, 'wall', 12, 19, level=1), health=1000),
        dict(role(89, 'wall', 11, 19, level=3), health=2000),
        dict(role(90, 'wall', 12, 20, level=3), health=2000),
    ])
    next(r for r in data['teamOur']['roles'] if r['id'] == 12)['pos'] = dict(x=11, y=20)
    for x in range(11, 14):
        for y in range(18, 21):
            if (x, y) not in {(12, 19), (11, 19), (12, 20), (11, 20)}:
                zone(data, 'stone', x, y)


class EconomicAuditTests(unittest.TestCase):
    def test_zero_gold_reconstruction_collects_sells_then_delivers_three_weapons(self):
        data = production(131, 0)
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles'] if r['roleType'] != 'rocket']
        session = main.GameSession(origin=1, strategy_mode='defense')
        seen, built = set(), []
        next_id = 1000
        for turn in range(131, 201):
            data['roundNo'] = turn
            response = session.handle(data)
            self.assertEqual(session.handle(deepcopy(data)), response)
            commands = response['roleCommandMap']
            prices = {x['name']: x['price'] for x in data['weaponShopList']}
            spent = sum(25 if c['action'] == 'build' and c['name'] != 'wall'
                        else prices[c['name']] * c['num'] if c['action'] == 'buy'
                        else 0 for c in commands.values())
            # Same-turn sales cannot fund a purchase or a construction action.
            self.assertLessEqual(spent, data['teamOur']['goldNum'])
            for actor, command in commands.items():
                char = next(r for r in data['teamOur']['roles'] if str(r['id']) == actor)
                action = command['action']
                seen.add(action)
                if action == 'move':
                    char['pos'] = command['targetPos'][0]
                elif action == 'collect':
                    mineral = next(z['neutralType'] for z in data['mapInfo']['zones']
                                   if z['pos'] == command['targetPos'][0])
                    char.setdefault('backpack', []).append(mineral)
                elif action == 'sell':
                    for _ in range(command['num']):
                        char['backpack'].remove(command['name'])
                    price = next(i['price'] for i in data['vendorShopList'] if i['name'] == command['name'])
                    data['teamOur']['goldNum'] += price * command['num']
                elif action == 'build':
                    if command['name'] == 'wall':
                        char['backpack'].remove('stone')
                    else:
                        data['teamOur']['goldNum'] -= 25
                        built.append(command['name'])
                    cell = command['targetPos'][0]
                    data['teamOur']['roles'].append(dict(
                        role(next_id, command['name'], cell['x'], cell['y'], level=1), health=1000))
                    next_id += 1
                elif action == 'buy':
                    data['teamOur']['goldNum'] -= prices[command['name']] * command['num']
                    char.setdefault('backpack', []).extend([command['name']] * command['num'])
                else:
                    self.fail(f'unmodeled action {command}')
            data['lastRoundRoleActionResults'] = {actor: True for actor in commands}
            if len(built) == 3:
                break
        self.assertTrue({'collect', 'sell', 'build'} <= seen)
        self.assertEqual(Counter(built), Counter(rocket=2, railgun=1))
        self.assertLessEqual(turn, 200)

    def test_missing_weapon_forces_small_sale_and_uses_only_observed_proceeds(self):
        data = production(131, 20)
        data['teamOur']['roles'] = [r for r in data['teamOur']['roles'] if r['id'] != 12]
        data['teamOur']['roles'][0].update(backpack=['copper'], pos=dict(x=7, y=20))
        p = setup(data)
        job = p.plan.jobs['1']
        self.assertEqual(job.job_type, 'BUILD_WEAPON')
        p.execute_job(job, main.empty_response())
        self.assertEqual(p.v.commands['1'], {'action': 'sell', 'name': 'copper', 'num': 1})
        self.assertEqual(p.plan.budget.staged_gold, 20)
        self.assertEqual(job.job_type, 'BUILD_WEAPON')
        # Unchanged observation means the sale failed; retry sale, never assume funds.
        data['roundNo'] += 1
        p = setup(data)
        p.execute_job(p.plan.jobs['1'], main.empty_response())
        self.assertEqual(p.v.commands['1']['action'], 'sell')

    def test_missing_stone_releases_builder_to_income_without_losing_target(self):
        data = production(131, 0)
        data['mapInfo']['zones'] = [z for z in data['mapInfo']['zones'] if z['neutralType'] != 'stone']
        p = setup(data)
        job = next(j for j in p.plan.jobs.values() if j.job_type == 'BUILD_WALL')
        target = job.target
        p.execute_job(job, main.empty_response())
        self.assertEqual(p.v.commands[job.owner]['action'], 'collect')
        self.assertEqual(p.v.commands[job.owner]['targetPos'], [dict(x=6, y=23)])
        self.assertEqual((job.job_type, job.target), ('BUILD_WALL', target))

    def test_full_builder_sells_to_make_room_before_collecting_stone(self):
        data = production(131, 0)
        data['teamOur']['roles'][0].update(backpack=['copper'] * 100, backPackCapability=100, pos=dict(x=7, y=20))
        p = setup(data)
        job = main.RoleJob('1', 'BUILD_WALL', None, 'START', 70, 131, 200)
        p.plan.jobs['1'] = job
        p.execute_job(job, main.empty_response())
        self.assertEqual(p.v.commands['1'], {'action': 'sell', 'name': 'copper', 'num': 100})
        self.assertEqual(p.plan.budget.staged_gold, 0)
        self.assertEqual(job.job_type, 'BUILD_WALL')

    def test_return_deadline_still_preempts_construction_income(self):
        data = production(200, 0)
        data['teamOur']['roles'][0]['backpack'] = ['copper'] * 100
        p = setup(data)
        _, report = p.run(main.empty_response())
        self.assertEqual(report['mode'], 'PRE_NIGHT')
        self.assertFalse(any(c['action'] in {'collect', 'sell', 'build', 'buy'} for c in p.v.commands.values()))

    def test_unreachable_ownerless_wall_reserve_no_longer_blocks_funded_upgrade(self):
        data = production(131, 100)
        isolated_wall(data)
        p = setup(data)
        wall = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'WALL_SERVICE')
        upgrade = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
        self.assertIsNone(wall.assigned_actor)
        self.assertEqual(p.plan.budget.reserved_gold['wall'], 0)
        p.execute_job(p.plan.jobs[upgrade.assigned_actor], main.empty_response())
        self.assertEqual(p.v.commands[upgrade.assigned_actor],
                         {'action': 'buy', 'name': 'WeaponUpgradeVoucher1', 'num': 1})
        self.assertEqual((p.plan.budget.staged_gold, p.plan.budget.committed_gold), (0, 100))

    def test_reachable_wall_owner_keeps_reserve_against_lower_priority_upgrade(self):
        data = production(131, 100)
        data['teamOur']['roles'].append(dict(role(88, 'wall', 12, 22, level=1), health=1000))
        p = setup(data)
        wall = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'WALL_SERVICE')
        upgrade = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
        self.assertIsNotNone(wall.assigned_actor)
        self.assertEqual(p.plan.budget.reserved_gold['wall'], 20)
        p.execute_job(p.plan.jobs[upgrade.assigned_actor], main.empty_response())
        self.assertEqual(upgrade.block_reason, 'BUDGET_BLOCKED')
        self.assertNotIn(upgrade.assigned_actor, p.v.commands)

    def test_held_wall_voucher_needs_no_new_reserve(self):
        data = production(131, 100)
        data['teamOur']['roles'].append(dict(role(88, 'wall', 12, 22, level=1), health=1000))
        data['teamOur']['roles'][2]['backpack'] = ['WallUpgradeVoucher1']
        p = setup(data)
        wall = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'WALL_SERVICE')
        self.assertEqual(wall.assigned_actor, '3')
        self.assertEqual(p.plan.budget.reserved_gold['wall'], 0)
        upgrade = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
        p.execute_job(p.plan.jobs[upgrade.assigned_actor], main.empty_response())
        self.assertEqual(p.v.commands[upgrade.assigned_actor]['name'], 'WeaponUpgradeVoucher1')

    def test_unavailable_item_and_unsellable_full_bag_cannot_capture_capital_owner(self):
        for unavailable in (False, True):
            with self.subTest(unavailable=unavailable):
                data = production(131, 100)
                data['teamOur']['roles'][2].update(backpack=['AcientTablet'] * 40, backPackCapability=40)
                if unavailable:
                    data['weaponShopList'] = [x for x in data['weaponShopList'] if x['name'] != 'WeaponUpgradeVoucher1']
                p = setup(data)
                goal = next(g for g in p.plan.capital_goals.values() if g.goal_type == 'UPGRADE')
                self.assertNotEqual(goal.assigned_actor, '3')
                if unavailable:
                    self.assertIsNone(goal.assigned_actor)
                    self.assertEqual(p.plan.budget.reserved_gold['upgrade'], 0)
                else:
                    self.assertIsNotNone(goal.assigned_actor)
                    goal.assigned_actor = '3'  # A stale owner does not make a full bag eligible.
                    p.schedule_production(200)
                    self.assertNotEqual(goal.assigned_actor, '3')
                    p.execute_job(p.plan.jobs[goal.assigned_actor], main.empty_response())
                    self.assertEqual(p.v.commands[goal.assigned_actor]['name'], 'WeaponUpgradeVoucher1')

    def test_used_voucher_waits_for_observed_upgrade_without_reserving_a_second_purchase(self):
        data = production(131, 100)
        data['teamOur']['roles'].append(dict(role(88, 'wall', 12, 22, level=1), health=1000))
        pioneer = data['teamOur']['roles'][2]
        pioneer.update(pos=dict(x=11, y=22), backpack=['WallUpgradeVoucher1'])
        session = main.GameSession(origin=1, strategy_mode='defense')
        first = session.handle(data)
        self.assertEqual(first['roleCommandMap']['3']['action'], 'use')
        self.assertEqual(first['roleCommandMap']['1']['name'], 'WeaponUpgradeVoucher1')
        # The observed voucher disappears without a level change. This is an
        # uncertain result, not evidence that purchasing another voucher is safe.
        data['roundNo'] = 132
        pioneer['backpack'] = []
        data['lastRoundRoleActionResults'] = {'1': False, '3': True}
        second = session.handle(data)
        wall = next(g for g in session.memory.strategic.plan.capital_goals.values()
                    if g.goal_type == 'WALL_SERVICE')
        self.assertEqual((wall.state, wall.last_action), ('VERIFY', 'use'))
        self.assertEqual(session.memory.strategic.plan.budget.reserved_gold['wall'], 0)
        self.assertFalse(any(c.get('name') == 'WallUpgradeVoucher1' for c in second['roleCommandMap'].values()))
        self.assertTrue(any(c == {'action': 'buy', 'name': 'WeaponUpgradeVoucher1', 'num': 1}
                            for c in second['roleCommandMap'].values()))


if __name__ == '__main__':
    unittest.main()
