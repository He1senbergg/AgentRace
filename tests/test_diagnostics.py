import json
import unittest
from unittest.mock import patch
from src import main3 as main
from test_actions import role, state


class TurnDiagnosticTests(unittest.TestCase):
    def test_actions_positions_feedback_and_unknown_phase(self):
        data = state(role(1, 'worker', 5, 5), vendorShopList=[{'name': 'iron', 'price': 3}])
        data['roundNo'] = 5
        data['mapInfo']['zones'] = [{'neutralType': 'iron', 'pos': {'x': 7, 'y': 5}}]
        session = main.GameSession(strategy_mode='legacy')
        with self.assertLogs(main.LOG, level='INFO') as logs:
            first = session.handle(data)
            data['roundNo'] = 6
            data['lastRoundRoleActionResults'] = {'1': False}
            data['errors'] = [{'errorCode': 4, 'description': 'SECRET'}]
            data['llmResp'] = 'SECRET'
            session.handle(data)
        records = [json.loads(line.split('[trace_turn] ', 1)[1]) for line in logs.output if '[trace_turn] ' in line]
        self.assertEqual(first['roleCommandMap']['1']['action'], 'move')
        self.assertEqual(records[0]['actions'][0]['action'], 'move')
        self.assertEqual(records[0]['roles'][0]['pos'], [5, 5])
        self.assertIsNone(records[0]['phase'])
        self.assertEqual(records[1]['feedback'], [{'id': '1', 'success': False}])
        self.assertTrue(records[1]['feedback_associated'])
        self.assertEqual(records[1]['error_codes'], [4])
        self.assertNotIn('SECRET', '\n'.join(logs.output))

    def test_invalid_input_sampling_and_duplicate_suppression(self):
        session = main.GameSession(strategy_mode='legacy')
        with self.assertLogs(main.LOG, level='INFO') as logs:
            for _ in range(100):
                self.assertEqual(session.handle({'roundNo': 'SECRET'}), main.empty_response())
        self.assertEqual(len(logs.output), 28)  # First 20 errors, then every tenth observation.
        self.assertIn('invalid_round_or_teamOur', logs.output[0])
        self.assertNotIn('SECRET', '\n'.join(logs.output))
        session = main.GameSession(strategy_mode='legacy')
        with self.assertLogs(main.LOG, level='INFO') as logs:
            for _ in range(5):
                session.handle(state())
        self.assertEqual(sum('[trace_turn] ' in line for line in logs.output), 1)

    def test_diagnostic_failure_does_not_replace_response(self):
        data = state(role(1, 'worker', 5, 5), vendorShopList=[{'name': 'iron', 'price': 3}])
        data['mapInfo']['zones'] = [{'neutralType': 'iron', 'pos': {'x': 6, 'y': 5}}]
        session = main.GameSession(strategy_mode='legacy')
        with patch.object(session, '_trace_turn', side_effect=ValueError('SECRET')):
            with self.assertLogs(main.LOG, level='ERROR') as logs:
                result = session.handle(data)
        self.assertEqual(result['roleCommandMap']['1']['action'], 'collect')
        self.assertEqual(session.handle(data), result)
        self.assertNotIn('SECRET', '\n'.join(logs.output))

    def test_every_turn_reports_actions_and_weapon_state_without_duplicate_logs(self):
        from test_defense import robot
        data = state(role(1, 'worker', 9, 10), role(2, 'rocket', 10, 10, level=1),
                     robot=[robot(50, 10, 12)])
        data['teamOur']['roles'][1].update(cooldown=0, attackRange=10)
        session = main.GameSession(origin=1, strategy_mode='shadow')
        session.diagnostic_turns = 10
        data['roundNo'] = 80
        with self.assertLogs(main.LOG, level='INFO') as logs:
            result = session.handle(data)
            self.assertEqual(session.handle(data), result)
        self.assertEqual(sum('[turn] ' in line for line in logs.output), 1)
        self.assertEqual(sum('[shadow_turn] ' in line for line in logs.output), 1)
        record = json.loads(logs.output[0].split('[turn] ', 1)[1])
        self.assertEqual(record['activity'], [{'id': '1', 'status': 'control_weapon', 'weapon': '2'}])
        self.assertEqual(record['weapons'][0]['cooldown'], 0)
        self.assertEqual(record['weapons'][0]['adjacent'], ['1'])
        self.assertEqual(record['actions'][0]['action'], 'attack')
        data['roundNo'] = 81
        data['teamOur']['roles'][1]['cooldown'] = 3
        with self.assertLogs(main.LOG, level='INFO') as logs:
            session.handle(data)
        record = json.loads(logs.output[0].split('[turn] ', 1)[1])
        self.assertEqual(record['activity'][0]['status'], 'no_command')
        self.assertEqual(record['weapons'][0]['cooldown'], 3)
        self.assertEqual(record['actions'], [])
