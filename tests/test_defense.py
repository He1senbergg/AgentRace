import unittest
import time
from src import main
from test_actions import role, state, zone, validator


def robot(actor, x, y, health=40, side='challenger'):
    return dict(id=actor, roleType='smallRobot', pos=dict(x=x, y=y), health=health, targetTeam=side)


class DefenseTests(unittest.TestCase):
    def test_other_side_robot_still_intercepts_ballistic_weapons(self):
        for kind, expected in (('gatling', {'50': 5}), ('railgun', {'50': 5, '51': 5})):
            data = state(role(1, 'worker', 9, 10), role(2, kind, 10, 10, level=1),
                         robot=[robot(50, 10, 11, 5, 'defender'), robot(51, 10, 12, 40)])
            defense = main.DefensePlanner(validator(data, main.Phase(1, 71)))
            self.assertEqual(defense.damage(defense.weapons[0], (10, 12)), expected)
            defense.fire()
            if kind == 'gatling':
                self.assertEqual(defense.v.commands, {})
            else:
                self.assertEqual(defense.v.commands['2']['targetPos'], [dict(x=10, y=12)])
                self.assertEqual(defense.remaining['51'], 35)

    def test_dizzy_reserves_targets_and_ignores_already_dizzy(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'worker', 2, 1),
                     robot=[robot(50, 30, 30), robot(51, 31, 30)])
        for character in data['teamOur']['roles']:
            character['backpack'] = ['DizzyWeapon']
        v = validator(data, main.Phase(1, 71))
        main.DefensePlanner(v).support()
        self.assertEqual(len(v.commands), 1)
        self.assertEqual(v.commands['1']['name'], 'DizzyWeapon')
        for entry in data['robot']:
            entry['abnormalState'] = 'dizzy'
        v = validator(data, main.Phase(1, 71))
        main.DefensePlanner(v).support()
        self.assertEqual(v.commands, {})

    def test_default_summon_uses_inventory_with_daily_quota_and_night_priority(self):
        data = state(role(1, 'worker', 1, 1))
        data['teamOur']['roles'][0]['backpack'] = ['SmallRobotSummonOrder'] * 20
        session = main.GameSession()
        for round_no in range(11):
            data['roundNo'] = round_no
            result = session.handle(data)
            self.assertEqual(bool(result['roleCommandMap']), round_no < 10)
            self.assertEqual(result, session.handle(data))
        data['roundNo'] = 70
        self.assertEqual(session.handle(data)['roleCommandMap'], {})
        data['roundNo'] = 130
        self.assertEqual(session.handle(data)['roleCommandMap']['1']['name'], 'SmallRobotSummonOrder')
        data['roundNo'] = 132
        self.assertEqual(session.handle(data)['roleCommandMap'], {})

    def test_low_level_wall_purchase_then_observed_repair(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'wall', 10, 10, level=1),
                     role(3, 'gatling', 11, 10, level=1), role(4, 'rocket', 11, 11, level=1),
                     weaponShopList=[dict(name='WallFixer', price=10)])
        zone(data, 'weaponShop', 8, 10)
        session = main.GameSession()
        self.assertEqual(session.handle(data)['roleCommandMap']['1'],
                         dict(action='buy', name='WallFixer', num=1))
        data['roundNo'] = 1
        data['teamOur']['roles'][0]['backpack'] = ['WallFixer']
        self.assertEqual(session.handle(data)['roleCommandMap']['1'],
                         dict(action='use', name='WallFixer', targetPos=[dict(x=10, y=10)]))
        data['roundNo'] = 2
        data['teamOur']['roles'][0]['backpack'] = []
        data['teamOur']['roles'][1]['health'] = 1000
        self.assertNotEqual(session.handle(data)['roleCommandMap'].get('1', {}).get('name'), 'WallFixer')

    def test_emergency_procurement_does_not_duplicate_worker_errands(self):
        data = state(role(1, 'worker', 3, 3), role(2, 'worker', 3, 4),
                     role(3, 'station', 10, 10, level=1),
                     weaponShopList=[dict(name='StationUpgradeVoucher1', price=100)])
        data['teamOur']['goldNum'] = 250
        zone(data, 'weaponShop', 4, 3)
        response = main.GameSession().handle(data)
        self.assertEqual(len(response['roleCommandMap']), 1)
        self.assertEqual(response['roleCommandMap']['1']['name'], 'StationUpgradeVoucher1')

    def test_fixer_repairs_each_wall_level_but_not_full_health(self):
        for level, maximum in ((1, 1000), (2, 1500), (3, 2000)):
            for health in (maximum - 1, maximum):
                with self.subTest(level=level, health=health):
                    data = state(role(1, 'worker', 9, 10),
                                 role(2, 'wall', 10, 10, level=level))
                    data['teamOur']['roles'][0]['backpack'] = ['WallFixer']
                    data['teamOur']['roles'][1]['health'] = health
                    v = validator(data, main.Phase(1, 71))
                    repaired = main.DefensePlanner(v).maintain()
                    self.assertEqual(repaired, health < maximum)
                    if repaired:
                        self.assertEqual(v.commands['1'], dict(action='use', name='WallFixer',
                                                              targetPos=[dict(x=10, y=10)]))
                    else:
                        self.assertEqual(v.commands, {})

    def test_medicine_and_bomb_use_observed_inventory(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'worker', 2, 1),
                     robot=[robot(50, 10, 10, 80), robot(51, 11, 10, 80)])
        data['teamOur']['roles'][0]['health'] = 20
        data['teamOur']['roles'][0]['backpack'] = ['Medicine']
        data['teamOur']['roles'][1]['backpack'] = ['Bomb']
        v = validator(data, main.Phase(1, 71))
        defense = main.DefensePlanner(v)
        defense.support()
        self.assertEqual(v.commands['1']['name'], 'Medicine')
        self.assertEqual(v.commands['2']['name'], 'Bomb')
        self.assertEqual(sum(defense.remaining.values()), 0)

    def test_full_callback_dense_robot_budget_and_repeat(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'worker', 12, 10),
                     role(3, 'rocket', 10, 10, level=3), role(4, 'rocket', 11, 10, level=3),
                     robot=[robot(100+i, 15+i%25, i//25, 800) for i in range(200)])
        data['roundNo'] = 70
        session = main.GameSession(origin=0)
        start = time.monotonic()
        response = session.handle(data)
        self.assertEqual(len(response['roleCommandMap']), 2)
        self.assertEqual(response, session.handle(data))
        self.assertLess(time.monotonic()-start, 4.0)

    def test_build_requires_confirmed_name_and_never_overwrites(self):
        data = state(role(1, 'worker', 9, 11), role(2, 'station', 10, 10, level=1))
        self.assertEqual(main.GameSession(rules=main.Rules(1, ())).handle(data)['roleCommandMap'], {})
        self.assertEqual(main.GameSession().handle(data)['roleCommandMap']['1']['name'], 'gatling')
        rules = main.Rules(None, (('confirmed-gun', 'gatling'),))
        result = main.GameSession(rules=rules).handle(data)['roleCommandMap']['1']
        self.assertEqual(result['action'], 'build')
        self.assertEqual(result['name'], 'confirmed-gun')
        cell = result['targetPos'][0]
        data['teamOur']['roles'].append(role(3, 'gatling', cell['x'], cell['y'], level=3))
        result = main.GameSession(rules=rules).handle(data)['roleCommandMap'].get('1', {})
        self.assertNotEqual(result.get('targetPos'), [cell])

    def test_wall_plan_preserves_cardinal_gaps(self):
        data = state(role(1, 'worker', 8, 12), role(2, 'station', 10, 10, level=3))
        data['teamOur']['roles'][0]['backpack'] = ['stone'] * 20
        v = validator(data, rules=main.Rules(2))
        self.assertTrue(main.DefensePlanner(v).construct())
        command = v.commands['1']
        self.assertEqual(command['action'], 'build')
        p = command['targetPos'][0]
        self.assertNotIn(p['x'], (10, 11))
        self.assertNotIn(p['y'], (10, 9))

    def test_emergency_upgrade_precedes_controller_use(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'station', 10, 10, level=1),
                     role(3, 'gatling', 9, 9, level=1), robot=[robot(50, 8, 9)])
        data['roundNo'] = 70
        data['teamOur']['roles'][0]['backpack'] = ['StationUpgradeVoucher1']
        v = validator(data, main.Phase(1, 71))
        defense = main.DefensePlanner(v)
        self.assertTrue(defense.maintain(emergency_only=True))
        defense.fire()
        self.assertEqual(v.commands['1']['name'], 'StationUpgradeVoucher1')
        self.assertNotIn('3', v.commands)

    def test_two_weapons_use_distinct_controllers(self):
        data = state(role(1, 'worker', 10, 9), role(2, 'worker', 8, 9),
                     role(3, 'gatling', 9, 10, level=1), role(4, 'railgun', 11, 10, level=1),
                     robot=[robot(50, 10, 12, 100)])
        v = validator(data, main.Phase(1, 71))
        main.DefensePlanner(v).fire()
        self.assertEqual(set(v.commands), {'3', '4'})
        self.assertEqual({c['controllerId'] for c in v.commands.values()}, {'1', '2'})

    def test_rocket_aoe_and_cooldown(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=2),
                     robot=[robot(50, 15, 10), robot(51, 16, 10), robot(52, 16, 11)])
        v = validator(data, main.Phase(1, 71))
        defense = main.DefensePlanner(v)
        self.assertEqual(defense.damage(v.world.roles['2'], (16, 10)), {'50': 10, '51': 20, '52': 10})
        defense.fire()
        self.assertEqual(len(v.commands['2']['targetPos']), 2)
        self.assertLess(sum(defense.remaining.values()), 120)
        data['teamOur']['roles'][1]['cooldown'] = 1
        v = validator(data, main.Phase(1, 71))
        main.DefensePlanner(v).fire()
        self.assertEqual(v.commands, {})

    def test_railgun_energy_and_gatling_interception(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'railgun', 10, 10, level=2),
                     robot=[robot(50, 11, 10, 5), robot(51, 12, 10, 30)])
        v = validator(data, main.Phase(1, 71))
        defense = main.DefensePlanner(v)
        self.assertEqual(defense.damage(v.world.roles['2'], (12, 10)), {'50': 5, '51': 15})
        v.world.roles['2']['roleType'] = 'gatling'
        self.assertEqual(defense.damage(v.world.roles['2'], (12, 10)), {'50': 5})

    def test_gatling_opposite_targets_stay_in_cone(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'gatling', 10, 10, level=3),
                     robot=[robot(50, 10, 12), robot(51, 10, 8)])
        v = validator(data, main.Phase(1, 71))
        main.DefensePlanner(v).fire()
        points = v.commands['2']['targetPos']
        self.assertEqual(len(points), 3)
        self.assertTrue(all(p['y'] > 10 for p in points) or all(p['y'] < 10 for p in points))

    def test_no_day_fire_or_task_pioneer_controller(self):
        data = state(role(1, 'pioneer', 9, 10), role(2, 'gatling', 10, 10, level=1),
                     phaseTask='active', robot=[robot(50, 10, 12)])
        for phase in (main.Phase(1, 1), main.Phase(1, 71)):
            v = validator(data, phase)
            defense = main.DefensePlanner(v)
            defense.fire()
            defense.position_controllers()
            self.assertEqual(v.commands, {})

    def test_return_before_night_and_hold_during_cooldown(self):
        data = state(role(1, 'worker', 1, 1), role(2, 'rocket', 10, 10, level=1, cooldown=2))
        v = validator(data, main.Phase(1, 65))
        main.DefensePlanner(v).position_controllers()
        self.assertEqual(v.commands['1']['action'], 'move')
        data['teamOur']['roles'][0]['pos'] = dict(x=9, y=10)
        zone(data, 'iron', 8, 10)
        data['vendorShopList'] = [dict(name='iron', price=3)]
        v = validator(data, main.Phase(1, 71))
        main.DefensePlanner(v).position_controllers()
        main.EconomyPlanner(v).workers()
        self.assertEqual(v.commands, {})
        self.assertIn('1', v.busy)

    def test_other_side_and_unknown_robot_target(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'gatling', 10, 10, level=1),
                     robot=[robot(50, 10, 12, side='defender'), robot(51, 10, 11, side=None)])
        v = validator(data, main.Phase(1, 71))
        defense = main.DefensePlanner(v)
        self.assertEqual(set(defense.robots), {'51'})
        defense.fire()
        self.assertEqual(v.commands['2']['targetPos'], [dict(x=10, y=11)])
