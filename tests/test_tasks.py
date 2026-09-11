import json
import unittest
from copy import deepcopy

from src import main3 as main
from test_actions import role, state, zone


def task_state(round_no=0, active=''):
    data = state(role(11, 'pioneer', 4, 5), phaseTask=active)
    data['roundNo'] = round_no
    zone(data, 'challengerTaskPoint2', 5, 5)
    zone(data, 'challengerTaskPoint2', 5, 6)
    data['teamOur']['playerTasks'] = [dict(taskPosition=dict(x=5, y=6), isValid=True,
                                         coldDownRounds=0, timeoutRounds=30)]
    return data


class TaskTests(unittest.TestCase):
    def test_submission_legality_feedback_uses_json_string_actor_key(self):
        for result in (True, False, None):
            session = main.GameSession(strategy_mode='legacy')
            session.handle(task_state(0, 'Question'))
            data = task_state(1, 'Question')
            data['llmResp'] = '{"answer":"candidate"}'
            session.handle(data)
            data = task_state(2, 'Question')
            data['lastRoundRoleActionResults'] = {} if result is None else {'11': result}
            prompt = session.handle(data)['prompt']
            context = json.JSONDecoder().raw_decode(prompt[prompt.index('{"task":'):])[0]
            self.assertIs(context['observation']['action_result'], result)
            self.assertEqual(session.memory.task_experience, [])

    def test_full_task_text_and_large_answer_are_not_silently_limited(self):
        task = 'BEGIN ' + '线索' * 40000 + ' END'
        data = task_state(0, task)
        session = main.GameSession(strategy_mode='legacy')
        prompt = session.handle(data)['prompt']
        self.assertIn(task, prompt)
        answer = '答案' * 40000
        data['roundNo'] = 1
        data['llmResp'] = json.dumps({'answer': answer}, ensure_ascii=False)
        self.assertEqual(session.handle(data)['roleCommandMap']['11']['taskAnswer'], answer)

    def test_skill_is_preserved_when_later_decision_omits_it(self):
        session = main.GameSession(strategy_mode='legacy')
        session.handle(task_state(0, 'Read city'))
        data = task_state(1, 'Read city')
        data['llmResp'] = '{"command":"cat city.txt","skill":"Read city.txt and extract the city key"}'
        session.handle(data)
        data['roundNo'] = 2
        data['lastCmdResult'] = '[exitCode:0]\nBeijing'
        self.assertIn('cat city.txt', session.handle(data)['prompt'])
        data['roundNo'] = 3
        data['llmResp'] = '{"answer":"Beijing"}'
        session.handle(data)
        session.handle(task_state(4))
        experience = session.memory.task_experience[0]
        self.assertEqual(experience['procedure'], 'Read city.txt and extract the city key')
        self.assertEqual(experience['last_command'], 'cat city.txt')
        self.assertIn('unverified', experience['outcome'])

    def test_overlapping_points_do_not_invent_task_timeout(self):
        data = task_state()
        data['teamOur']['playerTasks'][0]['timeoutRounds'] = 1
        zone(data, 'challengerTaskPoint1', 3, 5)
        data['teamOur']['playerTasks'].append(dict(taskPosition=dict(x=3, y=5), isValid=True,
                                                 coldDownRounds=0, timeoutRounds=100))
        session = main.GameSession(strategy_mode='legacy')
        session.handle(data)
        self.assertIsNone(session.memory.accepted_task)
        data['roundNo'] = 1
        data['phaseTask'] = 'Unknown selected task'
        session.handle(data)
        data['roundNo'] = 3
        self.assertTrue(session.handle(data)['prompt'])
        self.assertIsNone(session.memory.task['deadline'])

    def test_expired_old_task_error_does_not_expire_new_description(self):
        session = main.GameSession(strategy_mode='legacy')
        session.handle(task_state(0, 'Old task'))
        data = task_state(1, 'New task')
        data['errors'] = [{'errorCode': 1, 'description': 'old task expired'}]
        self.assertTrue(session.handle(data)['prompt'])
        self.assertFalse(session.memory.task['expired'])

    def test_strict_json_and_output_boundaries(self):
        for text in ('{"answer":"a","answer":"b"}', '{"answer":NaN}',
                     '{"command":"x","skill":Infinity}', '{"command":"x\\u0000y"}',
                     '{"answer":"\\ud800"}'):
            self.assertIsNone(main.parse_llm_decision(text))
        result = main.command_observation('[exitCode:0]\n' + 'x' * 70000 + '\n[TRUNCATED]')
        self.assertFalse(result['complete'])
        self.assertEqual(result['exit_code'], 0)
        self.assertIn('[TRUNCATED]', result['result'])
        self.assertIn('[LOCAL_CONTEXT_TRUNCATED]', result['result'])
        self.assertEqual(main.command_observation('[exitCode:-1]\nerror')['exit_code'], -1)

    def test_timeout_and_same_description_new_instance(self):
        session = main.GameSession(strategy_mode='legacy')
        data = task_state()
        data['teamOur']['playerTasks'][0]['timeoutRounds'] = 2
        session.handle(data)
        session.handle(task_state(1, 'Question'))
        response = session.handle(task_state(3, 'Question'))
        self.assertFalse(response['prompt'])
        self.assertTrue(session.memory.task['expired'])
        data = task_state(4)
        session.handle(data)
        data = task_state(5, 'Question')
        data['llmResp'] = '{"command":"old result"}'
        response = session.handle(data)
        self.assertTrue(response['prompt'])
        self.assertFalse(response['executeCmd'])

    def test_history_and_half_reset_only_preserves_labelled_experience(self):
        session = main.GameSession(strategy_mode='legacy')
        session.handle(task_state(0, 'Question'))
        data = task_state(1, 'Question')
        data['llmResp'] = '{"command":"inspect","skill":"procedure"}'
        session.handle(data)
        data['roundNo'] = 2
        data['lastCmdResult'] = '[exitCode:0]\nfirst discovery'
        session.handle(data)
        data['roundNo'] = 3
        data['llmResp'] = '{"command":"inspect again"}'
        session.handle(data)
        data['roundNo'] = 4
        data['lastCmdResult'] = '[exitCode:0]\nsecond discovery'
        self.assertIn('first discovery', session.handle(data)['prompt'])
        session.handle(task_state(5))
        session.handle(task_state(0))
        self.assertIsNone(session.memory.task)
        self.assertEqual(len(session.memory.task_experience), 1)
        self.assertIsNone(session.memory.news_pending)
        changed = task_state(1)
        changed['teamOur']['teamId'] = 99
        session.handle(changed)
        self.assertEqual(session.memory.task_experience, [])

    def test_accept_then_prompt_command_result_answer_and_unverified_end(self):
        session = main.GameSession(strategy_mode='legacy')
        self.assertEqual(session.handle(task_state())['roleCommandMap']['11']['action'], 'acceptTask')
        request = task_state(1, 'Read the sandbox data and return the city.')
        first = session.handle(request)
        self.assertTrue(first['prompt'])
        self.assertEqual(first, session.handle(request))
        self.assertEqual(session.memory.llm_calls_today, 0)
        request = task_state(2, request['phaseTask'])
        request['llmResp'] = json.dumps({'command': 'python --version', 'skill': 'Inspect the runtime'})
        command = session.handle(request)
        self.assertEqual(command['executeCmd'], 'python --version')
        self.assertFalse(command['prompt'])
        request['roundNo'] = 3
        request['lastCmdResult'] = '[exitCode:0]\nPython 3.11.10'
        self.assertIn('[exitCode:0]', session.handle(request)['prompt'])
        request['roundNo'] = 4
        request['llmResp'] = json.dumps({'answer': 'Beijing', 'skill': 'Read the city field'})
        self.assertEqual(session.handle(request)['roleCommandMap']['11']['taskAnswer'], 'Beijing')
        request = task_state(5)
        request['lastRoundRoleActionResults'] = {'11': True}
        session.handle(request)
        self.assertIsNone(session.memory.task)
        self.assertIn('unverified', session.memory.task_experience[0]['outcome'])

    def test_wrong_answer_while_active_uses_feedback(self):
        session = main.GameSession(strategy_mode='legacy')
        session.handle(task_state(0, 'Question'))
        data = task_state(1, 'Question')
        data['llmResp'] = '{"answer":"wrong"}'
        session.handle(data)
        data['roundNo'] = 2
        data['errors'] = [{'errorCode': 2, 'description': 'incorrect'}]
        response = session.handle(data)
        self.assertIn('incorrect', response['prompt'])
        self.assertEqual(response['roleCommandMap'], {})

    def test_missing_malformed_late_or_cross_task_results_not_executed(self):
        for reply in ('', 'not json', '[]', '{"command":"x","answer":"x"}',
                      '{"answer":5}', '{"command":""}'):
            session = main.GameSession(strategy_mode='legacy')
            session.handle(task_state(0, 'Question'))
            data = task_state(1, 'Question')
            data['llmResp'] = reply
            response = session.handle(data)
            self.assertFalse(response['executeCmd'])
            self.assertEqual(response['roleCommandMap'], {})
            self.assertTrue(response['prompt'])
        for round_no, description in ((2, 'Question'), (1, 'Different question')):
            session = main.GameSession(strategy_mode='legacy')
            session.handle(task_state(0, 'Question'))
            data = task_state(round_no, description)
            data['llmResp'] = '{"command":"stale"}'
            self.assertFalse(session.handle(data)['executeCmd'])

    def test_dead_displaced_or_ended_task_cannot_execute(self):
        for variant in ('dead', 'away', 'ended'):
            session = main.GameSession(strategy_mode='legacy')
            session.handle(task_state(0, 'Question'))
            data = task_state(1, 'Question')
            data['llmResp'] = '{"command":"stale"}'
            if variant == 'dead':
                data['teamOur']['roles'][0]['health'] = 0
            elif variant == 'away':
                data['teamOur']['roles'][0]['pos'] = dict(x=30, y=30)
            else:
                data['phaseTask'] = ''
            response = session.handle(data)
            self.assertFalse(response['executeCmd'])
            self.assertFalse(response['prompt'])

    def test_command_failure_markers_preserved(self):
        for result in ('[TIMEOUT]\npartial', '[JUDGER_ERROR]\nunavailable',
                       '[exitCode:1]\nfailed', '[exitCode:0]\npartial\n[TRUNCATED]'):
            session = main.GameSession(strategy_mode='legacy')
            session.handle(task_state(0, 'Question'))
            data = task_state(1, 'Question')
            data['llmResp'] = '{"command":"inspect"}'
            session.handle(data)
            data['roundNo'] = 2
            data['lastCmdResult'] = result
            response = session.handle(data)
            self.assertIn(json.dumps(result)[1:-1], response['prompt'])
            self.assertEqual(response['roleCommandMap'], {})

    def test_only_eligible_own_tasks_and_route(self):
        for field, value in (('isValid', False), ('coldDownRounds', 1), ('coldDownRounds', False)):
            data = task_state()
            data['teamOur']['playerTasks'][0][field] = value
            self.assertEqual(main.GameSession(strategy_mode='legacy').handle(data)['roleCommandMap'], {})
        data = task_state()
        data['teamOur']['roles'][0]['pos'] = dict(x=1, y=1)
        self.assertEqual(main.GameSession(strategy_mode='legacy').handle(data)['roleCommandMap']['11']['action'], 'move')

    def test_quota_gate_duplicate_reset_gap_and_rollback(self):
        def planner(w, m):
            return dict(roleCommandMap={}, prompt='reason', executeCmd='')
        session = main.GameSession(planner, strategy_mode='legacy')
        for round_no in range(3):
            data = task_state(round_no)
            response = session.handle(data)
            self.assertEqual(response, session.handle(data))
        self.assertEqual(session.memory.llm_calls_today, 3)
        before = deepcopy(session.memory)
        with self.assertRaises(ValueError):
            session.handle(task_state(3))
        self.assertEqual(session.memory, before)
        session.handle(task_state(130))
        self.assertEqual(session.memory.llm_calls_today, 1)
        with self.assertRaises(ValueError):
            session.handle(task_state(132))
        session.handle(task_state(131, 'Active'))
        self.assertEqual(session.memory.llm_calls_today, 1)
        illegal = main.GameSession(lambda w, m: dict(roleCommandMap={}, prompt='', executeCmd='x'), strategy_mode='legacy')
        with self.assertRaises(ValueError):
            illegal.handle(task_state())
        self.assertIsNone(illegal.memory)
