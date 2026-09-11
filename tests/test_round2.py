"""Closed-loop purchase delivery and budget regressions from Versus round2."""
import unittest
from src import main3 as main
from test_actions import role, state, zone, validator


class Round2Tests(unittest.TestCase):
    def test_blocked_front_releases_stocked_builder(self):
        data = self.opening()
        data['teamOur']['roles'][0]['backpack'] = ['stone'] * 8
        for i, (x, y) in enumerate(main.building_ring((30, 10), 2)):
            zone(data, 'stone', x, y)  # All construction sites occupied by observed mineral zones.
        v = validator(data)
        v.memory.wall_builder = {'actor': '1', 'goal': 8, 'building': True}
        d = main.DefensePlanner(v)
        self.assertFalse(d.construct())
        self.assertFalse(d.fortify())
        self.assertIsNone(v.memory.wall_builder)

    def test_global_controller_assignment_does_not_let_cooldown_gun_steal_operator(self):
        data = state(role(1, 'worker', 11, 10), role(4, 'pioneer', 9, 10),
                     role(2, 'rocket', 10, 10, level=1, cooldown=2),
                     role(3, 'rocket', 12, 10, level=1, cooldown=0))
        v = validator(data, main.Phase(1, 80))
        main.DefensePlanner(v).position_controllers()
        self.assertFalse(v.commands)
        self.assertEqual(v.busy, {'1', '4'})

    def test_first_day_batch_stone_builds_eight_walls_and_releases_worker(self):
        data = state(role(1, 'worker', 32, 7), role(2, 'rocket', 32, 8, level=1),
                     role(3, 'rocket', 32, 9, level=1), role(4, 'rocket', 31, 8, level=1),
                     role(5, 'station', 30, 10, level=1))
        data['teamOur']['roles'][-1]['health'] = 1500
        data['teamOur']['goldNum'] = 0
        zone(data, 'stone', 34, 7)
        session = main.GameSession(origin=1, strategy_mode='legacy')
        built = 0
        collected = 0
        for turn in range(8, 71):
            data['roundNo'] = turn
            c = session.handle(data)['roleCommandMap'].get('1', {})
            worker = data['teamOur']['roles'][0]
            if c.get('action') == 'move':
                worker['pos'] = c['targetPos'][0]
            elif c.get('action') == 'collect':
                collected += 1
                self.assertLessEqual(collected, 10)  # Initial mine stock is sufficient; no invented respawn.
                worker['backpack'].append('stone')
            elif c.get('action') == 'build':
                worker['backpack'].remove('stone')
                p = c['targetPos'][0]
                self.assertGreater((p['x']-30.5)*(-10.5)+(p['y']-9.5)*6, 0)
                data['teamOur']['roles'].append(role(100+turn, 'wall', p['x'], p['y'], level=1))
                built += 1
            data['lastRoundRoleActionResults'] = {'1': True} if c else {}
        self.assertEqual(built, 8)
        self.assertEqual(collected, 8)
        self.assertIsNone(session.memory.wall_builder)

    def opening(self):
        data = state(role(1, 'worker', 24, 19), role(2, 'rocket', 29, 11, level=1),
                     role(3, 'rocket', 29, 10, level=1), role(4, 'rocket', 30, 11, level=1),
                     role(5, 'station', 30, 10, level=1),
                     weaponShopList=[dict(name='Medicine', price=10), dict(name='WeaponUpgradeVoucher1', price=100)])
        data['teamOur']['roles'][0]['health'] = 220
        data['teamOur']['roles'][-1]['health'] = 1500
        data['teamOur']['goldNum'] = 145
        zone(data, 'weaponShop', 25, 20)
        return data

    def test_late_day_cash_really_becomes_upgrade_before_night(self):
        data = self.opening()
        session = main.GameSession(origin=1, strategy_mode='legacy')
        events = []
        for turn in range(56, 71):
            data['roundNo'] = turn
            result = session.handle(data)
            worker = data['teamOur']['roles'][0]
            c = result['roleCommandMap'].get('1')
            if not c:
                continue
            events.append(c['action'])
            if c['action'] == 'move':
                worker['pos'] = c['targetPos'][0]
            elif c['action'] == 'buy':
                self.assertEqual(c['name'], 'WeaponUpgradeVoucher1')
                worker['backpack'].append(c['name'])
                data['teamOur']['goldNum'] -= 100
            elif c['action'] == 'use':
                self.assertEqual(c['name'], 'WeaponUpgradeVoucher1')
                worker['backpack'].remove(c['name'])
                target = next(r for r in data['teamOur']['roles'] if r['pos'] == c['targetPos'][0])
                target['level'] = 2
                target['health'] = 1500
            data['lastRoundRoleActionResults'] = {'1': True}
        self.assertEqual(events.count('buy'), 1)
        self.assertEqual(events.count('use'), 1)
        self.assertTrue(any(r.get('level') == 2 for r in data['teamOur']['roles']))

    def test_full_wall_does_not_consume_money_when_weapon_is_unaffordable(self):
        data = self.opening()
        data['teamOur']['goldNum'] = 95
        wall = role(6, 'wall', 32, 12, level=1)
        wall['health'] = 1000
        data['teamOur']['roles'].append(wall)
        data['weaponShopList'].append(dict(name='WallUpgradeVoucher1', price=20))
        v = validator(data, main.Phase(2, 10))
        self.assertFalse(main.DefensePlanner(v).maintain())
        self.assertFalse(v.commands)

    def test_second_worker_can_collect_wall_stone_during_upgrade_delivery(self):
        data = self.opening()
        data['teamOur']['roles'][0]['backpack'] = ['WeaponUpgradeVoucher1']
        data['teamOur']['roles'].append(role(7, 'worker', 32, 9))
        zone(data, 'stone', 33, 9)
        v = validator(data, main.Phase(2, 1))
        v.memory.upgrade_trip = ('1', 'WeaponUpgradeVoucher1', (29, 11))
        result = main.plan_turn(v.world, v.memory)['roleCommandMap']
        self.assertEqual(result['1']['action'], 'move')
        self.assertEqual(result['7']['action'], 'collect')


if __name__ == '__main__':
    unittest.main()
