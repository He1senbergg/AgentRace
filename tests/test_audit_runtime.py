"""Protocol and task lifecycle regressions found by the V2.4 code audit."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from src import main3 as main
from src.agentrace import session as session_module
from test_tasks import task_state


class AuditRuntimeTests(unittest.TestCase):
    def test_default_defense_retires_task_without_a_new_task_job(self):
        session = main.GameSession()
        session.handle(task_state(0, 'Question'))
        answered = task_state(1, 'Question')
        answered['llmResp'] = '{"answer":"candidate","skill":"old procedure"}'
        self.assertEqual(session.handle(answered)['roleCommandMap']['11']['taskAnswer'], 'candidate')
        ended = task_state(2)
        ended['teamOur']['playerTasks'][0]['isValid'] = False
        ended['lastRoundRoleActionResults'] = {'11': True}
        ended['teamOur']['goldNum'] += 100
        session.handle(ended)
        self.assertNotEqual(session.memory.strategic.plan.jobs['11'].job_type, 'TASK')
        self.assertIsNone(session.memory.task)
        self.assertEqual(len(session.memory.task_experience), 1)
        self.assertIn('unverified', session.memory.task_experience[0]['outcome'])
        session.handle(ended)  # Cached delivery cannot archive twice.
        self.assertEqual(len(session.memory.task_experience), 1)
        prompt = session.handle(task_state(33, 'Question'))['prompt']
        context = json.loads(prompt[prompt.index('{"task":'):])
        self.assertEqual(context['previous_answer'], '')
        self.assertEqual(context['current_skill'], '')
        self.assertEqual(context['experience_unverified'][0]['procedure'], 'old procedure')

    def test_default_defense_same_text_after_timeout_is_a_fresh_task(self):
        session = main.GameSession()
        accepting = task_state(0)
        accepting['teamOur']['playerTasks'][0]['timeoutRounds'] = 2
        self.assertEqual(session.handle(accepting)['roleCommandMap']['11']['action'], 'acceptTask')
        session.handle(task_state(1, 'Question'))
        self.assertEqual(session.memory.task['deadline'], 2)
        self.assertFalse(session.handle(task_state(3, 'Question'))['prompt'])
        self.assertTrue(session.memory.task['expired'])
        ended = task_state(4)
        ended['teamOur']['playerTasks'][0]['isValid'] = False
        session.handle(ended)
        self.assertTrue(session.handle(task_state(34, 'Question'))['prompt'])
        self.assertFalse(session.memory.task['expired'])
        self.assertIsNone(session.memory.task['deadline'])

    def test_task_retirement_is_transactional_and_retry_archives_once(self):
        session = main.GameSession()
        session.handle(task_state(0, 'Question'))
        data = task_state(1, 'Question')
        data['llmResp'] = '{"command":"inspect","skill":"procedure"}'
        session.handle(data)
        before = deepcopy(session.memory)
        ended = task_state(2)
        ended['teamOur']['playerTasks'][0]['isValid'] = False
        with patch.object(session_module.StrategicPlanner, 'run', side_effect=RuntimeError('planner failed')):
            with self.assertRaises(RuntimeError):
                session.handle(ended)
        self.assertEqual(session.memory, before)
        session.handle(ended)
        self.assertIsNone(session.memory.task)
        self.assertEqual(len(session.memory.task_experience), 1)

    def test_gap_alone_does_not_invent_a_new_task_instance(self):
        session = main.GameSession()
        session.handle(task_state(0, 'Question'))
        data = task_state(1, 'Question')
        data['llmResp'] = '{"command":"inspect","skill":"same instance"}'
        session.handle(data)
        data = task_state(3, 'Question')
        data['lastCmdResult'] = '[exitCode:0]\nstale result'
        prompt = session.handle(data)['prompt']
        self.assertEqual(session.memory.task['skill'], 'same instance')
        self.assertIn('A round was missed', prompt)
        self.assertNotIn('stale result', prompt)
        self.assertEqual(session.memory.task_experience, [])

    def test_http_diagnostic_failure_keeps_committed_response_and_recovers(self):
        for failing_stage in ('before', 'after'):
            with self.subTest(failing_stage=failing_stage):
                session = main.GameSession(strategy_mode='legacy')
                client = main.app.test_client()
                calls = []

                def failed_log(message, *args, **kwargs):
                    calls.append(message)
                    if message.startswith('[trace_' + ('request' if failing_stage == 'before' else 'response') + ']'):
                        raise OSError('log sink unavailable')

                with patch.object(main, 'SESSION', session), patch.object(main, 'HTTP_DIAGNOSTIC_COUNT', 0):
                    with patch.object(main.LOG, 'info', side_effect=failed_log):
                        response = client.post('/', json=task_state(0))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json['roleCommandMap']['11']['action'], 'acceptTask')
                    self.assertEqual(response.json, session.response)
                    self.assertEqual(client.post('/', json=task_state(0)).json, response.json)
                    following = client.post('/', json=task_state(1, 'Question'))
                    self.assertEqual(following.status_code, 200)
                    self.assertTrue(following.json['prompt'])
                    self.assertEqual(session.memory.last_round, 1)
                self.assertTrue(calls)

    def test_http_error_logging_failure_still_returns_safe_json(self):
        session = main.GameSession(strategy_mode='legacy')
        with patch.object(main, 'SESSION', session), patch.object(main, 'HTTP_DIAGNOSTIC_COUNT', 3):
            client = main.app.test_client()
            with patch.object(main.LOG, 'error', side_effect=OSError('log sink unavailable')):
                response = client.post('/', data='{', content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, main.empty_response())
            self.assertIsNone(session.memory)
            response = client.post('/', json=task_state(0))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['roleCommandMap']['11']['action'], 'acceptTask')


if __name__ == '__main__':
    unittest.main()
