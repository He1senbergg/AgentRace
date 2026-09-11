"""Self/3.log failures, checked with synthetic observations, not battle simulation."""
import json
import unittest
from src import main3 as main
from test_actions import role, state, zone, validator
from test_defense import robot
from test_tasks import task_state


class StrategyRegressionTests(unittest.TestCase):
    def test_fifth_command_allowed_and_duplicate_is_idempotent(self):
        session = main.GameSession(origin=0, strategy_mode='legacy')
        session.handle(task_state(0, 'Question'))
        for turn in range(1, 9):
            data = task_state(turn, 'Question')
            if turn % 2:
                data['llmResp'] = json.dumps({'command': 'inspect'})
            else:
                data['lastCmdResult'] = '[exitCode:0]\nevidence'
            response = session.handle(data)
            self.assertEqual(response, session.handle(data))
            self.assertEqual(bool(response['executeCmd']), bool(turn % 2))
        self.assertEqual(session.memory.task['command_count'], 4)
        self.assertNotIn('FINAL ANSWER REQUIRED', response['prompt'])
        data = task_state(9, 'Question')
        data['llmResp'] = '{"command":"one more"}'
        response = session.handle(data)
        self.assertEqual(response['executeCmd'], 'one more')
        data = task_state(10, 'Question')
        data['lastCmdResult'] = '[exitCode:0]\nnew evidence'
        session.handle(data)
        data = task_state(11, 'Question')
        data['llmResp'] = '{"answer":"42"}'
        self.assertEqual(session.handle(data)['roleCommandMap']['11']['taskAnswer'], '42')

    def test_short_deadline_stops_commands_but_accepts_last_round_answer(self):
        for answer in (True, False):
            session = main.GameSession(origin=0, strategy_mode='legacy')
            data = task_state()
            data['teamOur']['playerTasks'][0]['timeoutRounds'] = 3
            self.assertEqual(session.handle(data)['roleCommandMap']['11']['action'], 'acceptTask')
            self.assertIn('FINAL ANSWER REQUIRED', session.handle(task_state(1, 'Q'))['prompt'])
            data = task_state(2, 'Q')
            data['llmResp'] = '{"command":"inspect"}'
            self.assertFalse(session.handle(data)['executeCmd'])
            data = task_state(3, 'Q')
            data['llmResp'] = '{"answer":"42"}' if answer else '{"command":"inspect"}'
            response = session.handle(data)
            self.assertFalse(response['prompt'])
            self.assertFalse(response['executeCmd'])
            self.assertEqual(bool(response['roleCommandMap']), answer)
            response = session.handle(task_state(4, 'Q'))
            self.assertEqual(response, main.empty_response())

    def test_task_budget_includes_return_and_rejects_unknown_timeout(self):
        data = task_state(45)
        data['teamOur']['roles'].append(role(20, 'rocket', 25, 5, level=1))
        data['teamOur']['playerTasks'][0]['timeoutRounds'] = 10
        response = main.GameSession(origin=0, strategy_mode='legacy').handle(data)
        self.assertEqual(response['roleCommandMap']['11']['action'], 'move')
        for timeout in (None, 0, True, -1):
            data = task_state()
            data['teamOur']['playerTasks'][0]['timeoutRounds'] = timeout
            self.assertEqual(main.GameSession(strategy_mode='legacy').handle(data)['roleCommandMap'], {})

    def test_idle_pioneer_prepares_defense(self):
        data = task_state()
        data['teamOur']['playerTasks'][0]['coldDownRounds'] = 30
        data['teamOur']['roles'].append(role(20, 'rocket', 12, 5, level=1))
        self.assertEqual(main.GameSession(strategy_mode='legacy').handle(data)['roleCommandMap']['11']['action'], 'move')

    def test_small_bag_is_sold_before_defense_and_income_not_prespent(self):
        data = state(role(1, 'worker', 7, 10), role(2, 'rocket', 10, 10, level=1),
                     vendorShopList=[dict(name='iron', price=3)])
        data['teamOur']['goldNum'] = 0
        data['teamOur']['roles'][0]['backpack'] = ['iron'] * 4
        zone(data, 'vendor', 5, 10)
        session = main.GameSession(origin=1, strategy_mode='legacy')
        actions = []
        for turn in (62, 63, 64):
            data['roundNo'] = turn
            response = session.handle(data)
            command = response['roleCommandMap'].get('1', {})
            actions.append(command.get('action'))
            if command.get('action') == 'move':
                data['teamOur']['roles'][0]['pos'] = command['targetPos'][0]
            elif command.get('action') == 'sell':
                self.assertEqual(command['num'], 4)
                data['teamOur']['roles'][0]['backpack'] = []
                data['teamOur']['goldNum'] = 12
        self.assertEqual(actions, ['move', 'sell', 'move'])
        v = validator(data)
        v.world.characters['1']['backpack'] = ['iron'] * 4
        v.world.characters['1']['cell'] = (6, 10)
        before = v.gold
        self.assertTrue(main.EconomyPlanner(v).cash_in(v.world.characters['1']))
        self.assertEqual(v.gold, before)

    def test_late_vendor_detour_does_not_take_gunner(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=1),
                     vendorShopList=[dict(name='iron', price=3)])
        data['teamOur']['roles'][0]['backpack'] = ['iron'] * 19
        zone(data, 'vendor', 1, 10)
        v = validator(data, main.Phase(1, 69))
        main.EconomyPlanner(v).liquidate()
        self.assertFalse(v.commands)
        main.DefensePlanner(v).position_controllers()
        self.assertIn('1', v.busy)

    def test_full_bag_with_few_minerals_still_goes_to_vendor(self):
        data = state(role(1, 'worker', 7, 10, backPackCapability=4),
                     vendorShopList=[dict(name='iron', price=3)])
        data['teamOur']['roles'][0]['health'] = 220
        data['teamOur']['roles'][0]['backpack'] = ['iron', 'Medicine', 'Medicine', 'Medicine']
        zone(data, 'vendor', 5, 10)
        self.assertEqual(main.GameSession(strategy_mode='legacy').handle(data)['roleCommandMap']['1']['action'], 'move')

    def test_disappearing_mine_does_not_interrupt_cash_delivery(self):
        data = state(role(1, 'worker', 9, 10), vendorShopList=[dict(name='iron', price=3)])
        data['teamOur']['goldNum'] = 0
        data['teamOur']['roles'][0]['backpack'] = ['iron'] * 6
        zone(data, 'iron', 10, 10)
        zone(data, 'vendor', 5, 10)
        session = main.GameSession(origin=1, strategy_mode='legacy')
        actions = []
        for turn in range(40, 45):
            data['roundNo'] = turn
            if turn == 41:
                data['mapInfo']['zones'] = [z for z in data['mapInfo']['zones'] if z['neutralType'] != 'iron']
                zone(data, 'iron', 30, 30)
            command = session.handle(data)['roleCommandMap'].get('1', {})
            actions.append(command.get('action'))
            if command.get('action') == 'move':
                data['teamOur']['roles'][0]['pos'] = command['targetPos'][0]
            elif command.get('action') == 'sell':
                break
        self.assertEqual(actions, ['move', 'move', 'move', 'sell'])

    def test_multiple_minerals_each_need_a_sale_turn(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=1),
                     vendorShopList=[dict(name='iron', price=3), dict(name='copper', price=5)])
        zone(data, 'vendor', 8, 10)
        data['teamOur']['roles'][0]['backpack'] = ['iron', 'copper']
        v = validator(data, main.Phase(1, 67))
        self.assertFalse(main.EconomyPlanner(v).cash_in(v.world.characters['1']))
        v = validator(data, main.Phase(1, 66))
        self.assertTrue(main.EconomyPlanner(v).cash_in(v.world.characters['1']))
        self.assertEqual(v.commands['1']['name'], 'copper')

    def test_survivor_moves_to_rocket_then_fires(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'gatling', 10, 10, level=1),
                     role(3, 'rocket', 7, 10, level=1),
                     robot=[robot(50, 12, 10), robot(51, 12, 11), robot(52, 13, 10)])
        data['roundNo'] = 92
        session = main.GameSession(origin=1, strategy_mode='legacy')
        response = session.handle(data)
        self.assertNotIn('2', response['roleCommandMap'])
        self.assertEqual(response['roleCommandMap']['1']['action'], 'move')
        data['teamOur']['roles'][0]['pos'] = response['roleCommandMap']['1']['targetPos'][0]
        data['roundNo'] = 93
        response = session.handle(data)
        self.assertEqual(response['roleCommandMap']['3']['controllerId'], '1')
        self.assertNotIn('1', response['roleCommandMap'])

    def test_cooldown_rocket_does_not_displace_ready_useful_gun(self):
        data = state(role(1, 'worker', 9, 10), role(2, 'gatling', 10, 10, level=1),
                     role(3, 'rocket', 7, 10, level=1, cooldown=3),
                     robot=[robot(50, 12, 10)])
        v = validator(data, main.Phase(1, 93))
        main.DefensePlanner(v).fire()
        self.assertEqual(v.commands['2']['controllerId'], '1')
        self.assertNotIn('3', v.commands)

    def test_command_status_logged_without_payload(self):
        data = task_state(0, 'SECRET TASK')
        data['lastCmdResult'] = '[exitCode:1]\nSECRET OUTPUT'
        data['llmResp'] = '{"command":"SECRET COMMAND"}'
        with self.assertLogs(main.LOG, level='INFO') as capture:
            main.GameSession(strategy_mode='legacy').handle(data)
        text = '\n'.join(capture.output)
        self.assertNotIn('SECRET', text)
        record = json.loads(next(line.split('[turn] ')[1] for line in capture.output if '[turn] ' in line))
        self.assertEqual(record['task']['command_result']['exit_code'], 1)
        self.assertEqual(record['task']['command_result']['status'], 'exited')
