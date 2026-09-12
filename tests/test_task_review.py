"""Independent boundary regressions from the local review of Task R1."""
import json
import unittest

from src.agentrace.task_protocol import task_output_matches
from test_task_protocol_r1 import r1_start, r1_reply, r1_state


class TaskReviewTests(unittest.TestCase):
    def test_json_source_numbers_do_not_lose_precision(self):
        for answer, output in (
            ('9007199254740993.0', '9007199254740992.0'),
            ('1.00000000000000001', '1.0'),
            ('1e-400', '0.0'),
            ('true', '1'),
            ('"1"', '1'),
        ):
            with self.subTest(answer=answer, output=output):
                self.assertFalse(task_output_matches('{"n":' + answer + '}', '{"n":' + output + '}'))

    def test_equal_json_source_numbers_preserve_semantic_equivalence(self):
        self.assertTrue(task_output_matches('{"n":[1.25,1000]}', '{"n":[125e-2,1e3]}'))
        self.assertFalse(task_output_matches('{"n":1}', 'debug\n{"n":1}'))

    def test_extreme_numeric_source_fails_closed_without_crashing(self):
        self.assertFalse(task_output_matches('{"n":1e-9999999999999999999999}', '{"n":0}'))

    def test_rounded_candidate_is_rejected_in_real_task_flow(self):
        session = r1_start(timeout=6)
        r1_reply(session, 2, {'command': 'compute'})
        session.handle(r1_state(3, lastCmdResult='[exitCode:0]\n{"n":9007199254740992.0}'))
        response = r1_reply(session, 4, {'command': 'continue',
                                        'candidate_answer': '{"n":9007199254740993.0}',
                                        'candidate_source_round': 3})
        self.assertFalse(response['roleCommandMap'])
        self.assertIsNone(session.memory.task['candidate'])
        self.assertEqual(session.memory.task['candidate_reject_reason'], 'source_missing_or_output_mismatch')

    def test_final_rejected_command_can_still_supply_verified_candidate(self):
        for mode in ('defense', 'legacy', 'shadow'):
            session = r1_start(timeout=6, mode=mode)
            r1_reply(session, 2, {'command': 'compute'})
            session.handle(r1_state(3, lastCmdResult='[exitCode:0]\n42'))
            response = r1_reply(session, 4, {'command': 'continue', 'candidate_answer': '42',
                                            'candidate_source_round': 3})
            self.assertEqual(response['roleCommandMap']['11']['taskAnswer'], '42')
            self.assertFalse(response['executeCmd'])
            self.assertFalse(response['prompt'])
            self.assertEqual(session.memory.task['last_protocol_error'], 'final_answer_required')

    def test_final_candidate_extraction_does_not_relax_other_validation(self):
        for fields in ({'candidate_answer': '43'}, {'candidate_source_round': 2},
                       {'command': []}, {'unexpected': 'field'}):
            session = r1_start(timeout=6)
            r1_reply(session, 2, {'command': 'compute'})
            session.handle(r1_state(3, lastCmdResult='[exitCode:0]\n42'))
            value = {'command': 'continue', 'candidate_answer': '42', 'candidate_source_round': 3, **fields}
            response = r1_reply(session, 4, value)
            self.assertFalse(response['roleCommandMap'])
            self.assertFalse(response['executeCmd'])
            self.assertIsNone(session.memory.task['candidate'])


if __name__ == '__main__':
    unittest.main()
