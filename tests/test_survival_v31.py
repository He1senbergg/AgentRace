"""V3.1 scheduler regressions, including independent multi-turn transitions.

These are behavioural checks, not proof of official combat survival.
"""
from collections import Counter
from copy import deepcopy
import logging
import unittest
from unittest.mock import patch

from src.agentrace.session import GameSession
from src.agentrace.model import inventory
from tests.test_survival_v3 import actor, battle_state, planner
from tests import test_survival_v3 as original_fixtures
from tools.simulate_survival import DayEngine, footprint, make_role


def with_target(data):
    data['robot']['roles'] = [make_role(800, 'largeRobot', (14, 18), health=500, targetTeam='challenger')]
    return data


def attack_count(response):
    return sum(c['action'] == 'attack' for c in response['roleCommandMap'].values())


class QuietCase(unittest.TestCase):
    def setUp(self):
        self.old_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(self.old_disable)


class WallReservationTests(QuietCase):
    def builder(self, bag):
        data = battle_state()
        actor(data, 2).update(pos={'x': 13, 'y': 20}, backpack=list(bag))
        p = planner(data)
        p.jobs['2'] = dict(kind='wall', stage='quarry', quota=8, cell=(12, 24))
        return data, p

    def test_mixed_full_bag_sells_only_copper_and_preserves_batch(self):
        data, p = self.builder(['stone'] * 8 + ['copper'] * 92)
        self.assertTrue(p.sell('2', force=True))
        self.assertEqual(p.v.commands['2'], {'action': 'sell', 'name': 'copper', 'num': 92})
        self.assertEqual(p.jobs['2']['kind'], 'wall')
        engine = DayEngine(data)
        engine.apply(dict(roleCommandMap=p.v.commands, prompt='', executeCmd=''))
        self.assertEqual(Counter(actor(engine.data, 2)['backpack']), Counter(stone=8))

    def test_iron_is_not_blocked_by_wall_reservation(self):
        _, p = self.builder(['stone'] * 8 + ['iron'] * 4)
        self.assertTrue(p.sell('2'))
        self.assertEqual(p.v.commands['2'], {'action': 'sell', 'name': 'iron', 'num': 4})
        self.assertEqual(p.jobs['2']['kind'], 'wall')

    def test_surplus_stone_above_batch_is_saleable(self):
        data, p = self.builder(['stone'] * 20)
        self.assertTrue(p.sell('2', force=True))
        self.assertEqual(p.v.commands['2'], {'action': 'sell', 'name': 'stone', 'num': 12})
        engine = DayEngine(data)
        engine.apply(dict(roleCommandMap=p.v.commands, prompt='', executeCmd=''))
        self.assertEqual(Counter(actor(engine.data, 2)['backpack']), Counter(stone=8))

    def test_income_cannot_erase_pending_wall_batch(self):
        data, p = self.builder(['stone'] * 8)
        before = deepcopy(p.jobs['2'])
        self.assertFalse(p.income('2'))
        self.assertEqual(p.jobs['2'], before)
        self.assertFalse(p.sell('2', force=True))
        self.assertEqual(p.v.commands, {})
        engine = DayEngine(data)
        engine.apply(dict(roleCommandMap=p.v.commands, prompt='', executeCmd=''))
        self.assertEqual(Counter(actor(engine.data, 2)['backpack']), Counter(stone=8))

    def test_material_reservation_survives_service_job_switch(self):
        _, p = self.builder(['stone'] * 8)
        self.assertEqual(p.reserved_wall_stone('2'), 8)
        p.jobs['2'] = dict(kind='service', target='5', item='WeaponUpgradeVoucher1')
        self.assertFalse(p.sell('2', force=True))
        self.assertEqual(p.wall_reservations['2'], 8)

    def test_finished_target_releases_stone_reservation(self):
        _, p = self.builder(['stone'] * 8)
        p.reserved_wall_stone('2')
        p.v.wall_count = p.wall_target
        self.assertTrue(p.sell('2', force=True))
        self.assertEqual(p.v.commands['2']['num'], 8)
        self.assertNotIn('2', p.wall_reservations)
        self.assertEqual(p.jobs['2']['kind'], 'sell')

    def test_last_three_missing_walls_do_not_reserve_twenty_stones(self):
        _, p = self.builder(['stone'] * 20)
        p.v.wall_count = p.wall_target - 3
        self.assertTrue(p.sell('2', force=True))
        self.assertEqual(p.v.commands['2']['num'], 17)

    def test_owner_death_releases_reservation(self):
        data, p = self.builder(['stone'] * 8)
        p.reserved_wall_stone('2')
        data['roundNo'] = 2
        actor(data, 2)['health'] = 0
        q = planner(data, p.memory)
        self.assertNotIn('2', q.wall_reservations)

    def test_rejected_sale_neither_erases_job_nor_reserves_action(self):
        _, p = self.builder(['copper'] * 100)
        before = deepcopy(p.jobs['2'])
        with patch.object(p.v, 'add', return_value=False):
            self.assertFalse(p.sell('2', force=True))
        self.assertEqual(p.jobs['2'], before)
        self.assertNotIn('2', p.v.busy)
        self.assertTrue(any(e['event'] == 'action_rejected' for e in p.events))

    def test_nonbuilder_can_still_sell_all_stone(self):
        data = battle_state()
        actor(data, 2).update(pos={'x': 13, 'y': 20}, backpack=['stone'] * 20)
        p = planner(data)
        self.assertTrue(p.sell('2', force=True))
        self.assertEqual(p.v.commands['2']['num'], 20)

    def test_empty_builder_can_fund_while_stone_is_unavailable(self):
        data, p = self.builder([])
        data['mapInfo']['zones'] = [z for z in data['mapInfo']['zones'] if z['neutralType'] != 'stone']
        p = planner(data)
        p.jobs['2'] = dict(kind='wall', stage='quarry', quota=8, cell=(12, 24))
        self.assertTrue(p.income('2'))
        self.assertIn(p.v.commands['2']['action'], {'move', 'collect'})
        self.assertEqual(p.jobs['2']['kind'], 'wall')
        self.assertTrue(any(e['event'] == 'wall_funding' for e in p.events))

    def test_full_copper_bag_resumes_construction_over_260_transitions(self):
        data = battle_state(round_no=131)
        actor(data, 2).update(pos={'x': 13, 'y': 20}, backpack=['copper'] * 100)
        engine = DayEngine(data, respawn=True)
        session = GameSession(strategy_mode='survival', origin=1)
        first = session.handle(deepcopy(data))
        self.assertEqual(first['roleCommandMap']['2'], {'action': 'sell', 'name': 'copper', 'num': 100})
        engine.apply(first)
        for _ in range(259):
            engine.apply(session.handle(deepcopy(engine.data)))
        self.assertFalse(engine.rejected)
        self.assertEqual(Counter(actor(engine.data, 2)['backpack'])['copper'], 0)
        self.assertGreaterEqual(sum(r['roleType'] == 'wall' for r in engine.data['teamOur']['roles']), 12)


class PaidDeliveryTests(QuietCase):
    def test_adjacent_voucher_on_last_daylight_tick_is_used(self):
        data = battle_state(round_no=70, levels=(2, 2, 2))
        actor(data, 2)['backpack'] = ['WeaponUpgradeVoucher2']
        p = planner(data)
        self.assertEqual(p.return_cost('2'), 0)
        self.assertTrue(p.held_delivery('2'))
        self.assertEqual(p.v.commands['2']['action'], 'use')

    def test_wall_errand_cannot_reduce_next_night_fire(self):
        data = battle_state(round_no=70, levels=(2, 2, 2))
        actor(data, 2)['backpack'] = ['WallUpgradeVoucher1']
        data['teamOur']['roles'].append(make_role(100, 'wall', (12, 24)))
        engine = DayEngine(data)
        session = GameSession(strategy_mode='survival', origin=1)
        engine.apply(session.handle(deepcopy(data)))
        self.assertEqual(actor(engine.data, 2)['pos'], {'x': 8, 'y': 23})
        self.assertEqual(attack_count(session.handle(with_target(deepcopy(engine.data)))), 3)

    def test_far_old_target_does_not_hide_legal_adjacent_wall(self):
        data = battle_state(round_no=70)
        actor(data, 2)['backpack'] = ['WallUpgradeVoucher1']
        data['teamOur']['roles'] += [make_role(100, 'wall', (12, 24)), make_role(101, 'wall', (8, 24))]
        p = planner(data)
        p.jobs['2'] = dict(kind='service', target='100', item='WallUpgradeVoucher1')
        self.assertTrue(p.held_delivery('2'))
        self.assertEqual(p.jobs['2']['target'], '101')
        self.assertEqual(p.v.commands['2']['targetPos'], [{'x': 8, 'y': 24}])

    def test_failed_deadline_does_not_claim_target_or_replace_job(self):
        data = battle_state(round_no=70)
        actor(data, 2)['backpack'] = ['WallUpgradeVoucher1']
        data['teamOur']['roles'].append(make_role(100, 'wall', (12, 24)))
        p = planner(data)
        p.jobs['2'] = dict(kind='wall', stage='build', quota=8)
        before = deepcopy(p.jobs['2'])
        self.assertFalse(p.held_delivery('2'))
        self.assertEqual(p.jobs['2'], before)
        self.assertFalse(p.claimed)
        self.assertTrue(any(e['event'] == 'delivery_deferred' for e in p.events))

    def test_deadline_counts_use_and_return_but_no_purchase_margin(self):
        data = battle_state(round_no=69)
        p = planner(data)
        route = [(8, 23), (7, 23)]
        # Move, use, then one move back needs three ticks, not two.
        self.assertFalse(p.delivery_fits('2', route))
        p = planner(battle_state(round_no=68))
        self.assertTrue(p.delivery_fits('2', route))

    def test_day70_deferral_is_delivered_after_day_boundary(self):
        data = battle_state(round_no=70, levels=(2, 2, 2))
        actor(data, 2)['backpack'] = ['WallUpgradeVoucher1']
        data['teamOur']['roles'].append(make_role(100, 'wall', (12, 24)))
        engine = DayEngine(data)
        session = GameSession(strategy_mode='survival', origin=1)
        for _ in range(76):
            engine.apply(session.handle(deepcopy(engine.data)))
        self.assertEqual(engine.stats['use:WallUpgradeVoucher1'], 1)
        self.assertEqual(actor(engine.data, 100)['level'], 2)
        self.assertFalse(engine.rejected)

    def test_retry_another_target_after_validator_rejection(self):
        data = battle_state(levels=(2, 2, 2))
        actor(data, 2)['backpack'] = ['WeaponUpgradeVoucher2']
        p = planner(data)
        p.jobs['2'] = dict(kind='service', target='5', item='WeaponUpgradeVoucher2')
        original = p.v.add

        def reject_first(actor_id, command):
            if command.get('targetPos') == [{'x': 8, 'y': 22}]:
                return False
            return original(actor_id, command)

        with patch.object(p.v, 'add', side_effect=reject_first):
            self.assertTrue(p.held_delivery('2'))
        self.assertEqual(p.jobs['2']['target'], '6')
        self.assertEqual(p.claimed, {'6'})
        self.assertTrue(any(e['event'] == 'action_rejected' for e in p.events))

    def test_dynamic_blocked_target_does_not_hide_available_cannon(self):
        data = battle_state(levels=(2, 2, 2))
        actor(data, 2).update(pos={'x': 10, 'y': 24}, backpack=['WeaponUpgradeVoucher2'])
        actor(data, 3)['pos'] = {'x': 8, 'y': 23}
        actor(data, 4)['pos'] = {'x': 11, 'y': 24}
        for cell in [(7, 21), (7, 22), (7, 23), (8, 21)]:
            data['mapInfo']['zones'].append(dict(neutralType='obstacle', pos=dict(x=cell[0], y=cell[1])))
        p = planner(data)
        p.jobs['2'] = dict(kind='service', target='5', item='WeaponUpgradeVoucher2')
        self.assertIsNotNone(p.route('2', {(8, 22)}, static=True))
        self.assertIsNone(p.route('2', {(8, 22)}))
        self.assertTrue(p.held_delivery('2'))
        self.assertEqual(p.jobs['2']['target'], '6')

    def test_two_couriers_do_not_modify_same_gun(self):
        data = battle_state(levels=(2, 2, 2))
        actor(data, 2)['backpack'] = ['WeaponUpgradeVoucher2']
        actor(data, 3)['backpack'] = ['WeaponUpgradeVoucher2']
        p = planner(data)
        self.assertTrue(p.held_delivery('2'))
        self.assertTrue(p.held_delivery('3'))
        cells = [tuple(c['targetPos'][0].values()) for c in p.v.commands.values()]
        self.assertEqual(len(cells), len(set(cells)))

    def test_busy_actor_cannot_overwrite_existing_job_or_claim(self):
        data = battle_state(levels=(2, 2, 2))
        actor(data, 2)['backpack'] = ['WeaponUpgradeVoucher2']
        p = planner(data)
        p.v.busy.add('2')
        self.assertFalse(p.held_delivery('2'))
        self.assertEqual(p.claimed, set())
        self.assertNotIn('2', p.jobs)


class NightPriorityTests(QuietCase):
    def test_two_normal_vouchers_leave_all_three_guns_firing(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        for a in (2, 3):
            actor(data, a)['backpack'] = ['WeaponUpgradeVoucher2']
        out = GameSession(strategy_mode='survival', origin=1).handle(data)
        self.assertEqual(attack_count(out), 3)
        self.assertFalse(any(c['action'] == 'use' for c in out['roleCommandMap'].values()))

    def test_critical_base_uses_voucher_and_remaining_two_guns_fire(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        actor(data, 1)['health'] = 1
        actor(data, 2)['backpack'] = ['StationUpgradeVoucher1']
        out = GameSession(strategy_mode='survival', origin=1).handle(data)
        self.assertEqual(out['roleCommandMap']['2'], dict(action='use', name='StationUpgradeVoucher1', targetPos=[dict(x=9, y=22)]))
        self.assertEqual(attack_count(out), 2)
        self.assertFalse(any(c.get('controllerId') == '2' for c in out['roleCommandMap'].values()))

    def test_level_two_base_rescue_uses_level_two_voucher(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        actor(data, 1).update(level=2, health=1)
        actor(data, 2)['backpack'] = ['StationUpgradeVoucher2']
        out = GameSession(strategy_mode='survival', origin=1).handle(data)
        self.assertEqual(out['roleCommandMap']['2']['name'], 'StationUpgradeVoucher2')
        self.assertEqual(attack_count(out), 2)

    def test_full_health_base_upgrade_does_not_steal_fire(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        actor(data, 2)['backpack'] = ['StationUpgradeVoucher1']
        out = GameSession(strategy_mode='survival', origin=1).handle(data)
        self.assertEqual(attack_count(out), 3)
        self.assertFalse(any(c['action'] == 'use' for c in out['roleCommandMap'].values()))

    def test_wrong_voucher_does_not_trigger_fake_rescue(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        actor(data, 1).update(level=2, health=1)
        actor(data, 2)['backpack'] = ['StationUpgradeVoucher1']
        out = GameSession(strategy_mode='survival', origin=1).handle(data)
        self.assertEqual(attack_count(out), 3)
        self.assertFalse(any(c['action'] == 'use' for c in out['roleCommandMap'].values()))

    def test_rescue_prefers_spare_controller_in_cooldown_window(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        actor(data, 1)['health'] = 1
        actor(data, 3)['pos'] = {'x': 8, 'y': 21}
        actor(data, 5)['cooldown'] = 2
        for a in (2, 3):
            actor(data, a)['backpack'] = ['StationUpgradeVoucher1']
        out = GameSession(strategy_mode='survival', origin=1).handle(data)
        self.assertEqual(out['roleCommandMap']['3']['name'], 'StationUpgradeVoucher1')
        self.assertEqual(attack_count(out), 2)
        self.assertEqual(sum(c.get('name') == 'StationUpgradeVoucher1' for c in out['roleCommandMap'].values()), 1)

    def test_fire_matching_excludes_already_upgraded_gun(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        actor(data, 2)['backpack'] = ['WeaponUpgradeVoucher2']
        p = planner(data)
        self.assertTrue(p.held_delivery('2'))
        self.assertEqual(p.v.commands['2']['targetPos'], [dict(x=8, y=22)])
        p.night()
        self.assertEqual(sum(c['action'] == 'attack' for c in p.v.commands.values()), 2)
        self.assertNotIn('5', p.v.commands)
        self.assertFalse(any(e['event'] == 'action_rejected' for e in p.events))

    def test_idle_carrier_skips_fired_gun_and_upgrades_cooling_gun(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 3)))
        actor(data, 2)['pos'] = dict(x=7, y=22)
        actor(data, 3).update(pos=dict(x=8, y=23), backpack=['WeaponUpgradeVoucher2'])
        actor(data, 6)['cooldown'] = 2
        out = GameSession(strategy_mode='survival', origin=1).handle(data)
        self.assertEqual(out['roleCommandMap']['3'], dict(action='use', name='WeaponUpgradeVoucher2', targetPos=[dict(x=9, y=23)]))
        self.assertEqual(attack_count(out), 2)

    def test_night_rescue_never_sends_distant_carrier_travelling(self):
        data = with_target(battle_state(round_no=71, levels=(2, 2, 2)))
        actor(data, 1)['health'] = 1
        actor(data, 4)['backpack'] = ['StationUpgradeVoucher1']
        p = planner(data)
        self.assertFalse(p.rescue_base())
        self.assertEqual(p.v.commands, {})

    def test_night_fixture_is_nonoverlapping_and_has_three_controllers(self):
        data = original_fixtures.SurvivalNightFirePriorityTests._night_state(bag=['WeaponUpgradeVoucher1'])
        occupied = set()
        for role in data['teamOur']['roles']:
            self.assertFalse(occupied & footprint(role), role['id'])
            occupied.update(footprint(role))
        self.assertEqual(len(planner(data).matching()), 3)


if __name__ == '__main__':
    unittest.main()
