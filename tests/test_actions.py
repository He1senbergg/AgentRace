"""State legality from AI Spec, using explicit independent fixtures."""
import unittest
from copy import deepcopy
from src import main


def role(actor, kind, x, y, **fields):
    return dict(id=actor, roleType=kind, pos=dict(x=x, y=y), health=100,
                backpack=[], **fields)


def state(*roles, **fields):
    return dict(roundNo=0, teamOur=dict(teamId=7, type="challenger", goldNum=75, roles=list(roles)),
                mapInfo=dict(zones=[]), **fields)


def target(action, x, y, **fields):
    return dict(action=action, targetPos=[dict(x=x, y=y)], **fields)


def validator(data, phase=None, rules=None):
    memory = main.GameMemory((7, "challenger"))
    memory.phase = phase or main.Phase(1, 1)
    return main.ActionValidator(main.World(data), memory, rules)


def zone(data, kind, x, y):
    data['mapInfo']['zones'].append(dict(neutralType=kind, pos=dict(x=x, y=y)))


class ActionTests(unittest.TestCase):
    def test_health_numeric_boundaries_do_not_raise(self):
        for value, allowed in ((10**400, True), (float('inf'), False),
                               (float('nan'), False), (True, False), (0, False)):
            with self.subTest(value=str(value)):
                data = state(role(1, 'worker', 1, 1), role(2, 'gatling', 1, 2, level=1))
                data['teamOur']['roles'][0]['health'] = value
                self.assertEqual(validator(data).add('1', target('move', 2, 1)), allowed)
                self.assertEqual(validator(data, main.Phase(1, 71)).add(
                    '2', target('attack', 2, 2, controllerId='1')), allowed)

    def test_untargeted_consumables_reject_coordinates_without_reserving(self):
        data = state(role(1, 'worker', 1, 1))
        data['teamOur']['roles'][0]['backpack'] = ['Medicine', 'SmallRobotSummonOrder']
        v = validator(data)
        v.memory.summon_day_known = True
        for name in ('Medicine', 'SmallRobotSummonOrder'):
            self.assertFalse(v.add('1', target('use', 2, 2, name=name)))
        self.assertEqual(v.summons, 0)
        self.assertEqual(v.commands, {})
        self.assertTrue(v.add('1', dict(action='use', name='SmallRobotSummonOrder')))

    def test_shared_gold_and_rejection_is_atomic(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'pioneer', 2, 1),
                     weaponShopList=[dict(name='Medicine', price=40)])
        zone(data, 'weaponShop', 1, 2)
        v = validator(data)
        self.assertFalse(v.add('1', dict(action='buy', name='Medicine', num=2)))
        self.assertEqual(v.gold, 75)
        self.assertTrue(v.add('1', dict(action='buy', name='Medicine', num=1)))
        self.assertFalse(v.add('2', dict(action='buy', name='Medicine', num=1)))
        self.assertTrue(v.add('2', target('move', 3, 1)))
        self.assertEqual(v.gold, 35)

    def test_capacity_multiset_and_no_sale_credit(self):
        data = state(role(1, 'worker', 1, 1, backPackCapability=2), role(2, 'worker', 2, 1),
                     vendorShopList=[dict(name='iron', price=100)],
                     weaponShopList=[dict(name='Medicine', price=100)])
        data['teamOur']['roles'][0]['backpack'] = ['iron', 'iron']
        zone(data, 'vendor', 1, 2)
        zone(data, 'weaponShop', 2, 2)
        zone(data, 'iron', 0, 1)
        v = validator(data)
        self.assertFalse(v.add('1', target('collect', 0, 1)))
        self.assertFalse(v.add('1', dict(action='sell', name='iron', num=3)))
        self.assertTrue(v.add('1', dict(action='sell', name='iron', num=2)))
        self.assertFalse(v.add('2', dict(action='buy', name='Medicine', num=1)))
        self.assertEqual(v.gold, 75)

    def test_collect_same_mine_night_and_wrong_actor(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'worker', 2, 1), role(3, 'pioneer', 0, 1))
        zone(data, 'stone', 1, 2)
        v = validator(data, main.Phase(1, 71))
        self.assertFalse(v.add('3', target('collect', 1, 2)))
        self.assertTrue(v.add('1', target('collect', 1, 2)))
        self.assertTrue(v.add('2', target('collect', 1, 2)))
        self.assertFalse(validator(data).add('1', target('collect', 0, 0)))

    def test_move_conflicts_and_active_task_lock(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'worker', 2, 1), role(3, 'pioneer', 4, 4), phaseTask='active')
        v = validator(data)
        self.assertFalse(v.add('1', target('move', 2, 1)))
        self.assertTrue(v.add('1', target('move', 2, 2)))
        self.assertFalse(v.add('2', target('move', 2, 2)))
        self.assertFalse(v.add('3', target('move', 5, 5)))

    def test_attack_cone_controller_cooldown_and_runtime_range(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'gatling', 10, 10, level=2, attackRange=4),
                     role(3, 'rocket', 8, 10, level='level1', cooldown=1))
        command = target('attack', 14, 10, controllerId='1')
        command['targetPos'].append(dict(x=10, y=14))
        self.assertFalse(validator(data).add('2', command))
        v = validator(data, main.Phase(1, 71))
        self.assertFalse(v.add('3', target('attack', 8, 12, controllerId='1')))
        invalid = deepcopy(command)
        invalid['targetPos'][1] = dict(x=9, y=14)
        self.assertFalse(v.add('2', invalid))
        self.assertTrue(v.add('2', command))  # Exactly 90 degrees, runtime range=4.
        self.assertFalse(v.add('1', target('move', 9, 11)))
        self.assertFalse(v.add('3', target('attack', 8, 12, controllerId='1')))
        data['teamOur']['roles'][1]['attackRange'] = 3
        self.assertFalse(validator(data, main.Phase(1, 71)).add('2', command))

    def test_build_regions_counts_budget_and_unknown_rules(self):
        data = state(role(1, 'worker', 9, 11), role(2, 'worker', 12, 11),
                     role(3, 'station', 10, 10, level=1))
        rules = main.Rules(2, (('gatling', 'gatling'),))
        data['teamOur']['roles'][0]['backpack'] = ['stone', 'stone']
        self.assertFalse(validator(data).add('1', target('build', 9, 10, name='gatling')))
        v = validator(data, rules=rules)
        self.assertFalse(v.add('1', target('build', 8, 11, name='gatling')))
        self.assertTrue(v.add('1', target('build', 8, 11, name='wall')))
        self.assertTrue(v.add('2', target('build', 12, 10, name='gatling')))
        self.assertEqual(v.gold, 50)
        self.assertFalse(validator(data, main.Phase(1, 71), rules).add('1', target('build', 9, 10, name='gatling')))
        data['teamOur']['roles'] += [role(10+i, 'gatling', 9+i, 8, level=1) for i in range(3)]
        self.assertFalse(validator(data, rules=rules).add('2', target('build', 12, 10, name='gatling')))

    def test_upgrade_and_remove_do_not_double_modify_building(self):
        data = state(role(1, 'worker', 8, 10), role(2, 'worker', 8, 9), role(3, 'wall', 9, 10, level=1))
        data['teamOur']['roles'][0]['backpack'] = ['WallUpgradeVoucher1', 'WallUpgradeVoucher2']
        v = validator(data, main.Phase(1, 71))
        self.assertFalse(v.add('1', target('use', 9, 10, name='WallUpgradeVoucher2')))
        self.assertTrue(v.add('1', target('use', 9, 10, name='WallUpgradeVoucher1')))
        self.assertFalse(v.add('2', target('remove', 9, 10)))
        self.assertTrue(validator(data, main.Phase(1, 71)).add('2', target('remove', 9, 10)))

    def test_task_own_side_multicell_and_submission(self):
        data = state(role(1, 'pioneer', 6, 5), role(2, 'worker', 5, 5))
        zone(data, 'challengerTaskPoint2', 4, 4)
        zone(data, 'challengerTaskPoint2', 5, 4)
        data['teamOur']['playerTasks'] = [dict(taskPosition=dict(x=4, y=4), isValid=True, coldDownRounds=0)]
        self.assertTrue(validator(data).add('1', dict(action='acceptTask')))
        self.assertFalse(validator(data).add('2', dict(action='acceptTask')))
        self.assertFalse(validator(data).add('1', dict(action='submitAnswer', taskAnswer='x')))
        data['phaseTask'] = 'active'
        self.assertTrue(validator(data).add('1', dict(action='submitAnswer', taskAnswer='x')))
        self.assertFalse(validator(data).add('1', dict(action='acceptTask')))
        data['phaseTask'] = ''
        data['teamOur']['playerTasks'][0]['coldDownRounds'] = 1
        self.assertFalse(validator(data).add('1', dict(action='acceptTask')))

    def test_treasure_inventory_and_drop(self):
        data = state(role(1, 'pioneer', 1, 1))
        data['teamOur']['roles'][0]['backpack'] = ['StarSand', 'StarSand']
        v = validator(data)
        self.assertFalse(v.add('1', target('summonTreasure', 1, 2, item=['StarSand']*3)))
        self.assertTrue(v.add('1', target('summonTreasure', 1, 2, item=['StarSand']*2)))
        self.assertTrue(validator(data).add('1', dict(action='drop', name='StarSand')))
        self.assertFalse(validator(data).add('1', dict(action='use', name='StarSand')))

    def test_consumables_and_summon_daily_limit(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'pioneer', 2, 1))
        for r in data['teamOur']['roles']:
            r['backpack'] = ['medicine', 'Bomb', 'SmallRobotSummonOrder']
        self.assertTrue(validator(data).add('1', dict(action='use', name='Medicine')))
        self.assertTrue(validator(data).add('1', target('use', 40, 31, name='Bomb')))
        v = validator(data)
        v.memory.summon_day_known = True
        v.summons = 9
        self.assertTrue(v.add('1', dict(action='use', name='SmallRobotSummonOrder')))
        self.assertFalse(v.add('2', dict(action='use', name='SmallRobotSummonOrder')))
        self.assertFalse(validator(data).add('1', dict(action='use', name='SmallRobotSummonOrder')))

    def test_malformed_inventory_prices_and_level(self):
        for malformed in (None, {}, [None], [dict(name='stone')]):
            data = state(role(1, 'worker', 1, 1))
            data['teamOur']['roles'][0]['backpack'] = malformed
            zone(data, 'stone', 1, 2)
            self.assertFalse(validator(data).add('1', target('collect', 1, 2)))
        self.assertEqual(main.shop_prices([dict(name='x', price=1), dict(name='x', price=1)]), {})
        self.assertEqual(main.shop_prices([dict(name='x', price=True)]), {})
        self.assertIsNone(main.level_of(dict(level=[])))
        data = state(role(1, 'worker', 1, 1), role(2, [], 2, 2))
        self.assertFalse(validator(data).add('1', target('remove', 2, 2)))


class EconomyTests(unittest.TestCase):
    def test_default_callback_collect_then_sell_from_observation(self):
        data = state(role(1, 'worker', 1, 1), vendorShopList=[dict(name='iron', price=3)])
        zone(data, 'iron', 2, 2)
        session = main.GameSession()
        self.assertEqual(session.handle(data)['roleCommandMap']['1']['action'], 'collect')
        # Actual next state, not an assumed collect success, drives selling.
        data['roundNo'] = 1
        data['teamOur']['roles'][0]['backpack'] = ['iron']*20
        zone(data, 'vendor', 0, 1)
        self.assertEqual(session.handle(data)['roleCommandMap']['1'], dict(action='sell', name='iron', num=20))

    def test_dynamic_mine_and_two_workers_no_move_collision(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'worker', 2, 1), vendorShopList=[dict(name='iron', price=3)])
        zone(data, 'iron', 5, 5)
        session = main.GameSession()
        commands = session.handle(data)['roleCommandMap']
        positions = [c['targetPos'][0] for c in commands.values()]
        self.assertEqual(len({(p['x'], p['y']) for p in positions}), len(positions))
        data['roundNo'] = 1
        data['mapInfo']['zones'] = []
        self.assertEqual(session.handle(data)['roleCommandMap'], {})

    def test_dynamic_purchase_item_and_budget(self):
        data = state(role(1, 'pioneer', 1, 1), weaponShopList=[dict(name='NewTaskItem', price=15)])
        zone(data, 'weaponShop', 2, 1)
        v = validator(data)
        self.assertTrue(main.EconomyPlanner(v).purchase('1', 'NewTaskItem', 2))
        self.assertEqual(v.commands['1'], dict(action='buy', name='NewTaskItem', num=2))
        self.assertEqual(v.gold, 45)

    def test_final_gate_rolls_back_illegal_planner_output(self):
        data = state(role(1, 'worker', 1, 1))
        session = main.GameSession(lambda w, m: dict(roleCommandMap={'1': target('move', 40, 31)}, prompt='', executeCmd=''))
        with self.assertRaises(ValueError):
            session.handle(data)
        self.assertIsNone(session.memory)
        session.planner = lambda w, m: main.empty_response()
        self.assertEqual(session.handle(data), main.empty_response())

    def test_summon_duplicate_gap_and_day_reset(self):
        data = state(role(1, 'worker', 1, 1))
        data['teamOur']['roles'][0]['backpack'] = ['SmallRobotSummonOrder']*20
        def plan(world, memory):
            v = main.ActionValidator(world, memory)
            v.add('1', dict(action='use', name='SmallRobotSummonOrder'))
            return dict(roleCommandMap=v.commands, prompt='', executeCmd='')
        session = main.GameSession(plan)
        for round_no in range(11):
            data['roundNo'] = round_no
            response = session.handle(data)
            self.assertEqual(bool(response['roleCommandMap']), round_no < 10)
            self.assertEqual(session.handle(data), response)
        self.assertEqual(session.memory.summon_attempts, 10)
        data['roundNo'] = 130
        self.assertTrue(session.handle(data)['roleCommandMap'])
        self.assertEqual(session.memory.summon_attempts, 1)
        data['roundNo'] = 132
        self.assertFalse(session.handle(data)['roleCommandMap'])

    def test_purchase_full_inventory_does_not_travel(self):
        data = state(role(1, 'worker', 1, 1, backPackCapability=0), weaponShopList=[dict(name='Medicine', price=10)])
        zone(data, 'weaponShop', 5, 5)
        v = validator(data)
        self.assertFalse(main.EconomyPlanner(v).purchase('1', 'Medicine'))
        self.assertEqual(v.commands, {})
