"""Self5 failures: controller survival and final exploration, not a battle simulator."""
import unittest
from src import main3 as main
from test_actions import role, state, zone, validator
from test_defense import robot
from test_tasks import task_state


class Self5Tests(unittest.TestCase):
    def test_wounded_pioneer_buys_before_accepting_task(self):
        data = task_state()
        data['teamOur']['roles'][0]['health'] = 90
        data['teamOur']['roles'].extend(role(i, 'rocket', 10+i, 10, level=1) for i in (2, 3, 4))
        data['weaponShopList'] = [dict(name='Medicine', price=10)]
        zone(data, 'weaponShop', 3, 5)
        result = main.GameSession(origin=0).handle(data)['roleCommandMap']
        self.assertEqual(result['11'], dict(action='buy', name='Medicine', num=2))

    def test_cross_day_old_mine_does_not_override_much_better_mine(self):
        data = state(role(1, 'worker', 5, 5), vendorShopList=[dict(name='copper', price=5)])
        zone(data, 'copper', 6, 5)
        zone(data, 'copper', 30, 25)
        zone(data, 'vendor', 4, 5)
        v = validator(data, main.Phase(2, 1))
        v.memory.worker_mines['1'] = ('copper', (30, 25))
        main.EconomyPlanner(v).workers()
        self.assertEqual(v.commands['1']['action'], 'collect')
        self.assertEqual(v.commands['1']['targetPos'], [dict(x=6, y=5)])

    def test_heal_reserves_controller_before_ready_gun(self):
        worker = role(1, 'worker', 9, 10)
        worker['health'] = 40
        worker['backpack'] = ['Medicine']
        data = state(worker, role(2, 'rocket', 10, 10, level=2),
                     robot=[robot(50, 9, 12)])
        data['roundNo'] = 71
        result = main.GameSession(origin=1).handle(data)['roleCommandMap']
        self.assertEqual(result['1'], {'action': 'use', 'name': 'Medicine'})
        self.assertNotIn('2', result)

    def test_cooldown_repositions_to_lower_threat_without_leaving_gun(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=2, cooldown=2),
                     robot=[robot(50, 6, 10)])
        v = validator(data, main.Phase(1, 71))
        defense = main.DefensePlanner(v)
        defense.position_controllers()
        command = v.commands['1']
        p = main.position(command['targetPos'][0])
        self.assertEqual(command['action'], 'move')
        self.assertLess(defense.exposure(p), defense.exposure((9, 10)))
        self.assertLessEqual(main.distance(p, (10, 10)), 1)

    def test_medicine_procurement_preserves_construction_budget_and_deadline(self):
        data = state(role(1, 'worker', 8, 10), role(2, 'rocket', 10, 10, level=1),
                     weaponShopList=[dict(name='Medicine', price=10)])
        zone(data, 'weaponShop', 7, 10)
        data['teamOur']['goldNum'] = 69
        v = validator(data)
        main.DefensePlanner(v).provision()
        self.assertFalse(v.commands)
        data['teamOur']['goldNum'] = 70
        v = validator(data)
        main.DefensePlanner(v).provision()
        self.assertEqual(v.commands['1'], dict(action='buy', name='Medicine', num=2))
        v = validator(data, main.Phase(1, 70))
        main.DefensePlanner(v).provision()
        self.assertFalse(v.commands)

    def test_cooldown_does_not_walk_around_gun_to_distant_safe_side(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=2, cooldown=2),
                     role(3, 'wall', 10, 9, level=1), role(4, 'wall', 10, 11, level=1),
                     robot=[robot(50, 6, 10)])
        v = validator(data, main.Phase(1, 71))
        main.DefensePlanner(v).position_controllers()
        self.assertFalse(v.commands)

    def test_last_exploration_round_has_result_answer_and_feedback_room(self):
        session = main.GameSession(origin=0)
        data = task_state()
        data['teamOur']['playerTasks'][0]['timeoutRounds'] = 6
        session.handle(data)
        session.handle(task_state(1, 'Question'))
        data = task_state(2, 'Question')
        data['llmResp'] = 'invalid'
        session.handle(data)
        data = task_state(3, 'Question')
        data['llmResp'] = '{"command":"inspect"}'
        self.assertEqual(session.handle(data)['executeCmd'], 'inspect')
        self.assertEqual(session.handle(data)['executeCmd'], 'inspect')
        data = task_state(4, 'Question')
        data['lastCmdResult'] = '[exitCode:0]\nevidence'
        self.assertIn('FINAL ANSWER REQUIRED', session.handle(data)['prompt'])
        data = task_state(5, 'Question')
        data['llmResp'] = '{"answer":"verified"}'
        self.assertEqual(session.handle(data)['roleCommandMap']['11']['taskAnswer'], 'verified')


if __name__ == '__main__':
    unittest.main()
