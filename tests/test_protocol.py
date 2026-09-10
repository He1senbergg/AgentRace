import unittest
from unittest.mock import patch
from src import main


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_fresh_empty_response(self):
        a = main.empty_response()
        a['roleCommandMap']['1'] = {}
        self.assertEqual(main.empty_response(), {'roleCommandMap': {}, 'prompt': '', 'executeCmd': ''})

    def test_duplicate_nonfinite_and_invalid_utf8_requests_are_atomic(self):
        session = main.GameSession()
        with patch.object(main, 'SESSION', session):
            for body in (b'{"roundNo":0,"roundNo":1,"teamOur":{"teamId":7,"type":"challenger"}}',
                         b'{"roundNo":0,"teamOur":{"teamId":7,"type":"challenger"},"x":NaN}',
                         b'{"text":"\xff"}', b'{"text":"\\ud800"}'):
                with self.assertLogs(main.LOG, level='ERROR'):
                    response = self.client.post('/', data=body, content_type='application/json')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, main.empty_response())
                self.assertIsNone(session.memory)
            valid = {'roundNo': 0, 'teamOur': {'teamId': 7, 'type': 'challenger'}}
            self.assertEqual(self.client.post('/', json=valid).status_code, 200)
            self.assertEqual(session.memory.last_round, 0)

    def test_bad_requests_recover(self):
        for body in ('', '{', 'null', '[]', 'true', '"文本"'):
            with self.subTest(body=body), self.assertLogs(main.LOG, level='ERROR'):
                result = self.client.post('/', data=body, content_type='application/json')
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json, main.empty_response())
        self.assertEqual(self.client.post('/', json={'roundNo': 1}).status_code, 200)

    def test_internal_exception_and_invalid_response(self):
        with patch.object(main, 'callback', side_effect=RuntimeError('SECRET')), self.assertLogs(main.LOG) as logs:
            self.assertEqual(self.client.post('/', json={}).json, main.empty_response())
        self.assertNotIn('SECRET', str(logs.output))
        for response in (None, {}, {'roleCommandMap': {}, 'prompt': [], 'executeCmd': ''}):
            with patch.object(main, 'callback', return_value=response), self.assertLogs(main.LOG):
                self.assertEqual(self.client.post('/', json={}).json, main.empty_response())

    def test_unicode_response(self):
        result = {'roleCommandMap': {}, 'prompt': '保留中文线索', 'executeCmd': ''}
        with patch.object(main, 'callback', return_value=result):
            response = self.client.post('/', json={})
        self.assertEqual(response.json, result)
        self.assertIn('中文'.encode(), response.data)

    def test_command_shapes(self):
        good = [
            {'action': 'move', 'targetPos': [{'x': 0, 'y': 31}]},
            {'action': 'acceptTask'}, {'action': 'buy', 'name': 'Medicine', 'num': 1},
            {'action': 'attack', 'controllerId': '10010', 'targetPos': [{'x': 40, 'y': 0}]},
        ]
        bad = [None, {'action': []}, {'action': 'noop'}, {'action': 'move'},
               {'action': 'move', 'targetPos': {'x': 1, 'y': 1}},
               {'action': 'move', 'targetPos': [{'x': True, 'y': 0}]},
               {'action': 'move', 'targetPos': [{'x': 41, 'y': 0}]},
               {'action': 'buy', 'name': 'Medicine', 'num': True},
               {'action': 'use', 'name': 'Bomb'},
               {'action': 'acceptTask', 'unknown': 1}]
        for command in good:
            self.assertTrue(main.validate_command_shape(command), command)
        for command in bad:
            self.assertFalse(main.validate_command_shape(command), command)
