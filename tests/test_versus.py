"""Versus regression: mirrored construction and uninterrupted upgrade logistics."""
import unittest
from src import main3 as main
from test_actions import role, state, zone, validator


class VersusTests(unittest.TestCase):
    def test_nearby_stone_for_walls_is_daytime_bounded(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=1),
                     role(3, 'rocket', 10, 11, level=1), role(4, 'rocket', 11, 11, level=1))
        zone(data, 'stone', 8, 10)
        v = validator(data, main.Phase(2, 1))
        self.assertTrue(main.DefensePlanner(v).fortify())
        self.assertEqual(v.commands['1']['action'], 'collect')
        for phase in [main.Phase(2, 70), main.Phase(2, 71)]:
            self.assertFalse(main.DefensePlanner(validator(data, phase)).fortify())

    def test_critical_courier_heals_without_losing_delivery(self):
        worker = role(1, 'worker', 9, 10)
        worker['health'] = 40
        worker['backpack'] = ['Medicine', 'WeaponUpgradeVoucher1']
        data = state(worker, role(2, 'rocket', 10, 10, level=1))
        v = validator(data)
        v.memory.upgrade_trip = ('1', 'WeaponUpgradeVoucher1', (10, 10))
        result = main.plan_turn(v.world, v.memory)['roleCommandMap']
        self.assertEqual(result['1']['name'], 'Medicine')
        self.assertIsNotNone(v.memory.upgrade_trip)

    def test_unbought_weapon_trip_yields_to_critical_base(self):
        data = state(role(1, 'worker', 7, 10), role(2, 'rocket', 10, 10, level=1),
                     role(3, 'station', 12, 10, level=1),
                     weaponShopList=[dict(name='StationUpgradeVoucher1', price=100)])
        v = validator(data)
        v.memory.upgrade_trip = ('1', 'WeaponUpgradeVoucher1', (10, 10))
        self.assertFalse(main.DefensePlanner(v).resume_upgrade())
        self.assertIsNone(v.memory.upgrade_trip)

    def test_both_bases_build_behind_base(self):
        for x, y in [(9, 22), (30, 10)]:
            data = state(role(1, 'worker', x-1, y-1), role(2, 'station', x, y, level=1))
            for _ in range(10):
                v = validator(data)
                main.DefensePlanner(v).construct()
                c = v.commands['1']
                if c['action'] == 'move':
                    data['teamOur']['roles'][0]['pos'] = c['targetPos'][0]
                else:
                    p = c['targetPos'][0]
                    self.assertLess((p['x']-x-.5)*(20-x-.5)+(p['y']-y+.5)*(16-y), 0)
                    self.assertIn((p['x'], p['y']), main.building_ring((x, y), 1))
                    break
            else:
                self.fail('No weapon built within ten moves')

    def test_delivery_precedes_sale_and_keeps_same_worker(self):
        worker = role(1, 'worker', 7, 10)
        worker['backpack'] = ['WeaponUpgradeVoucher1', 'copper'] * 1
        data = state(worker, role(2, 'rocket', 10, 10, level=1),
                     vendorShopList=[dict(name='copper', price=5)])
        zone(data, 'vendor', 6, 10)
        v = validator(data)
        v.memory.upgrade_trip = ('1', 'WeaponUpgradeVoucher1', (10, 10))
        response = main.plan_turn(v.world, v.memory)
        self.assertEqual(response['roleCommandMap']['1']['action'], 'move')
        self.assertEqual(v.memory.upgrade_trip[0], '1')
        worker['pos'] = dict(x=9, y=10)
        v.world = main.World(data)
        response = main.plan_turn(v.world, v.memory)
        self.assertEqual(response['roleCommandMap']['1']['name'], 'WeaponUpgradeVoucher1')
        self.assertIsNone(v.memory.upgrade_trip)

    def test_dead_courier_releases_trip(self):
        data = state(role(2, 'rocket', 10, 10, level=1))
        v = validator(data)
        v.memory.upgrade_trip = ('1', 'WeaponUpgradeVoucher1', (10, 10))
        self.assertFalse(main.DefensePlanner(v).resume_upgrade())
        self.assertIsNone(v.memory.upgrade_trip)

    def test_critical_base_reserves_funds_instead_of_weapon_or_medicine(self):
        data = state(role(1, 'worker', 7, 10), role(2, 'station', 10, 10, level=2),
                     role(3, 'rocket', 8, 9, level=1), role(4, 'rocket', 8, 8, level=1),
                     weaponShopList=[dict(name='StationUpgradeVoucher2', price=150),
                                     dict(name='WeaponUpgradeVoucher1', price=100), dict(name='Medicine', price=10)])
        data['teamOur']['goldNum'] = 138
        zone(data, 'weaponShop', 6, 10)
        v = validator(data)
        d = main.DefensePlanner(v)
        d.provision()
        d.maintain()
        self.assertFalse(v.commands)

    def test_base_reserve_only_blocks_spending_once_affordable(self):
        """Opt-in helper preserves spending until the station voucher is affordable."""
        data = state(role(1, 'worker', 7, 10), role(2, 'station', 10, 10, level=2),
                     role(3, 'rocket', 8, 9, level=1), role(4, 'rocket', 8, 8, level=1),
                     weaponShopList=[dict(name='StationUpgradeVoucher2', price=150),
                                     dict(name='WeaponUpgradeVoucher1', price=100), dict(name='Medicine', price=10)])
        data['teamOur']['goldNum'] = 138
        zone(data, 'weaponShop', 6, 10)
        v = validator(data)
        d = main.DefensePlanner(v, growth_mode=True)
        d.provision()
        d.maintain()
        self.assertEqual(v.commands.get('1'), {'action': 'buy', 'name': 'Medicine', 'num': 2})

        data['teamOur']['goldNum'] = 150
        v = validator(data)
        d = main.DefensePlanner(v, growth_mode=True)
        d.provision()
        self.assertFalse(v.commands)

    def test_breadth_first_even_when_level_three_is_affordable(self):
        data = state(role(1, 'worker', 7, 10), role(2, 'rocket', 9, 10, level=2),
                     role(3, 'rocket', 10, 10, level=1),
                     weaponShopList=[dict(name='WeaponUpgradeVoucher2', price=150),
                                     dict(name='WeaponUpgradeVoucher1', price=100)])
        data['teamOur']['goldNum'] = 150
        zone(data, 'weaponShop', 6, 10)
        v = validator(data)
        main.DefensePlanner(v).maintain()
        self.assertEqual(v.commands['1']['name'], 'WeaponUpgradeVoucher1')


if __name__ == '__main__':
    unittest.main()
