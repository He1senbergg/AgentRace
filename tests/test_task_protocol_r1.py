"""Task R1 regressions against REAL core modules; no Flask or model dependency.

Replies and sandbox outputs are explicit fixtures. No sandbox command is executed
locally, and passing these tests is not a statement about model accuracy.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from src.agentrace.session import GameSession
from src.agentrace.actions import ensure_valid_response
from src.agentrace.task_news import command_observation, parse_llm_decision
from src.agentrace.task_protocol import (
    TASK_CONTEXT_BUDGET, clip_task_text, decode_task_reply, make_task_context,
    render_task_prompt, select_task_experience, task_output_matches,
)
from src.agentrace import session as session_module


def r1_state(round_no=0, active="Question", timeout=10, **fields):
    return {"roundNo": round_no,
            "teamOur": {"teamId": 7, "type": "challenger", "goldNum": 75,
                        "roles": [{"id": 11, "roleType": "pioneer", "pos": {"x": 4, "y": 5},
                                   "health": 100, "backpack": []}],
                        "playerTasks": [{"taskPosition": {"x": 5, "y": 5}, "isValid": True,
                                         "coldDownRounds": 0, "timeoutRounds": timeout}]},
            "mapInfo": {"zones": [{"neutralType": "challengerTaskPoint2", "pos": {"x": 5, "y": 5}}]},
            "phaseTask": active, **fields}


def r1_context(response):
    return json.loads(response["prompt"][response["prompt"].index('{"task":'):])


def r1_start(timeout=10, mode="defense", text="Question"):
    session = GameSession(strategy_mode=mode)
    accepted = session.handle(r1_state(0, "", timeout))
    assert accepted["roleCommandMap"]["11"]["action"] == "acceptTask"
    session.handle(r1_state(1, text))
    return session


def r1_reply(session, round_no, value, text="Question"):
    return session.handle(r1_state(round_no, text, llmResp=json.dumps(value, ensure_ascii=False)))


class TaskR1ParserTests(unittest.TestCase):
    def test_detailed_errors_keep_strict_boundaries(self):
        cases = [(None, "missing_response"), ("", "missing_response"), ("[]", "object_required"),
                 ('{"answer":"a","answer":"b"}', "duplicate_key"),
                 ('{"answer":NaN}', "nonfinite_number"), ('{"answer":1e999}', "invalid_json"),
                 ('{"answer":"\\ud800"}', "invalid_unicode"), ('{"answer":{"x":1}}', "answer_must_be_string"),
                 ('{"command":[]}', "command_must_be_string"), ('{"command":""}', "command_empty_or_nul"),
                 ('{"answer":"a\\u0000b"}', "answer_empty_or_nul"),
                 ('{"answer":"a","command":"c"}', "choose_one_action"),
                 ('{"answer":"a","reason":"x"}', "unknown_field"),
                 ('{"command":"c","answer_from_stdout":1}', "stdout_flag_requires_command_and_boolean"),
                 ('{"answer":"a","answer_from_stdout":true}', "stdout_flag_requires_command_and_boolean")]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                decision, error = decode_task_reply(raw)
                self.assertIsNone(decision)
                self.assertEqual(error, expected)
                self.assertIsNone(parse_llm_decision(raw))

    def test_entire_fence_only_and_revalidation(self):
        self.assertEqual(parse_llm_decision('```json\n{"answer":"a"}\n```'), {"answer": "a"})
        for raw in ('Here is it: {"command":"c"}', '```json\n{"command":"a"}\n```\nmore',
                    '```json\n{"command":"a","command":"b"}\n```',
                    '```json\n{"command":"a"}\n```\n```json\n{"answer":"b"}\n```'):
            self.assertIsNone(parse_llm_decision(raw))

    def test_final_protocol_rejects_otherwise_valid_commands(self):
        decision, error = decode_task_reply('{"command":"inspect"}', answer_only=True)
        self.assertIsNone(decision)
        self.assertEqual(error, "final_answer_required")
        self.assertEqual(decode_task_reply('{"answer":"42","skill":"procedure"}', True)[0]["answer"], "42")

    def test_candidate_fields_are_paired_and_typed(self):
        for fields in ({"candidate_answer": "x"}, {"candidate_source_round": 2},
                       {"candidate_answer": "x", "candidate_source_round": True},
                       {"candidate_answer": "x", "candidate_source_round": -1},
                       {"candidate_answer": {}, "candidate_source_round": 1}):
            self.assertIsNone(decode_task_reply(json.dumps({"command": "c", **fields}))[0])
        good = {"command": "c", "candidate_answer": "x", "candidate_source_round": 2}
        self.assertEqual(decode_task_reply(json.dumps(good))[0], good)

    def test_no_lossy_answer_object_coercion(self):
        self.assertIsNone(decode_task_reply('{"answer":{"x":1}}')[0])
        value = {"answer": json.dumps({"x": 1})}
        self.assertEqual(decode_task_reply(json.dumps(value))[0], value)

    def test_source_equivalence_is_strict_about_types_and_whole_output(self):
        self.assertTrue(task_output_matches('{"b":2,"a":1}', '{ "a":1, "b":2 }\n'))
        self.assertFalse(task_output_matches('{"a":true}', '{"a":1}'))
        self.assertFalse(task_output_matches('{"a":1}', 'debug\n{"a":1}'))
        self.assertFalse(task_output_matches('Beijing', 'city=Beijing'))
        self.assertFalse(task_output_matches('{"a":2}', '{"a":1,"a":2}'))


class TaskR1ContextTests(unittest.TestCase):
    def new_task(self):
        return {"text": "Question", "history": [], "documents": "", "deadline": 10}

    def test_final_template_has_no_exploration_choice(self):
        prompt = render_task_prompt(self.new_task(), "result", [], 2)
        contract = prompt.split('\n{"task":', 1)[0]
        self.assertTrue(contract.startswith("FINAL ANSWER REQUIRED"))
        self.assertNotIn('"command"', contract)
        self.assertNotIn("candidate_source_round", contract)
        self.assertNotIn("answer_from_stdout", contract)

    def test_original_invalid_answer_and_specific_error_are_returned(self):
        session = r1_start()
        raw = '{"answer":{"city":"Beijing"}}'
        response = session.handle(r1_state(2, llmResp=raw))
        context = r1_context(response)
        self.assertEqual(context["observation"]["invalid_response"], raw)
        self.assertEqual(context["observation"]["protocol_error"], "answer_must_be_string")
        self.assertIn("FORMAT REPAIR", response["prompt"])
        self.assertFalse(response["executeCmd"])
        self.assertEqual(session.memory.task["prompt_stage"], "repair")
        repaired = r1_reply(session, 3, {"answer": '{"city":"Beijing"}'})
        self.assertEqual(repaired["roleCommandMap"]["11"]["taskAnswer"], '{"city":"Beijing"}')

    def test_invalid_response_is_bounded_not_silently_dropped(self):
        session = r1_start()
        response = session.handle(r1_state(2, llmResp="invalid" * 10000))
        observation = r1_context(response)["observation"]
        self.assertTrue(observation["invalid_response_truncated"])
        self.assertLessEqual(len(observation["invalid_response"]), 6000)
        self.assertIn("LOCAL_CONTEXT_TRUNCATED", observation["invalid_response"])

    def test_discovery_documents_appear_only_once(self):
        session = r1_start(text="Read TASK_DOC.md")
        self.assertEqual(session.memory.task["pending"][0], "discovery")
        document = "DOC_START_unique " + "line of documentation\n" * 500 + " DOC_END_unique"
        response = session.handle(r1_state(2, "Read TASK_DOC.md", lastCmdResult='[exitCode:0]\n' + document))
        self.assertEqual(response["prompt"].count("DOC_START_unique"), 1)
        self.assertEqual(response["prompt"].count("DOC_END_unique"), 1)
        self.assertLess(len(response["prompt"]), 18000)
        self.assertEqual(r1_context(response)["observation"]["document_ref"], "task_documents")
        self.assertFalse(session.memory.task["sources"])

    def test_current_observation_not_copied_to_recent_history(self):
        session = r1_start()
        r1_reply(session, 2, {"command": "inspect"})
        response = session.handle(r1_state(3, lastCmdResult="[exitCode:0]\nSINGLE_SOURCE_MARKER"))
        self.assertEqual(response["prompt"].count("SINGLE_SOURCE_MARKER"), 1)
        self.assertEqual(r1_context(response)["source_round"] if "source_round" in r1_context(response) else
                         r1_context(response)["observation"]["source_round"], 3)

    def test_auxiliary_budget_and_full_task_preserved(self):
        task = self.new_task()
        task.update(text="始" + "题目" * 40000 + "终", documents="D" * 50000,
                    history=["H" * 10000 for _ in range(8)], answer="A" * 80000,
                    command="C" * 80000, skill="S" * 10000)
        context = make_task_context(task, {"result": "R" * 50000}, [], 2, True)
        self.assertEqual(context["task"], task["text"])
        size = len(json.dumps({k: v for k, v in context.items() if k != "task"}, ensure_ascii=False))
        self.assertLessEqual(size, TASK_CONTEXT_BUDGET)
        self.assertTrue(context["context_omissions"])

    def test_unrelated_experience_and_raw_old_results_not_injected(self):
        entries = [{"task": "Sort integer array ascending", "procedure": "UNRELATED", "outcome": "success"},
                   {"task": "Read WEATHER_TASK.md for Beijing", "procedure": "Use the documented weather API",
                    "last_command": "STALE_SECRET", "last_observation": ["OLD_TEMPERATURE"], "outcome": "success"}]
        selected = select_task_experience(entries, "Read WEATHER_TASK.md for Shanghai")
        self.assertEqual(len(selected), 1)
        text = json.dumps(selected)
        self.assertNotIn("STALE_SECRET", text)
        self.assertNotIn("OLD_TEMPERATURE", text)
        self.assertNotIn("UNRELATED", text)
        self.assertIn("unverified", selected[0]["outcome"])

    def test_skill_retained_but_never_converted_to_answer(self):
        session = r1_start(timeout=4)
        r1_reply(session, 2, {"command": "inspect", "skill": 'partial answer {"city":"Beijing"}'})
        session.handle(r1_state(3, lastCmdResult="[exitCode:0]\nBeijing"))
        response = r1_reply(session, 4, {"command": "again"})
        self.assertFalse(response["roleCommandMap"])
        self.assertFalse(response["prompt"])
        self.assertIsNone(session.memory.task["candidate"])

    def test_clip_has_exact_budget_and_marker(self):
        for size in (0, 1, 25, 40, 41, 200):
            self.assertLessEqual(len(clip_task_text("0123456789" * 100, size)), size)
        self.assertIn("LOCAL_CONTEXT_TRUNCATED", clip_task_text("x" * 1000, 100))


class TaskR1RuntimeTests(unittest.TestCase):
    def test_declared_stdout_submits_in_both_real_modes_and_cached_request(self):
        for mode in ("defense", "legacy"):
            with self.subTest(mode=mode):
                session = r1_start(mode=mode)
                r1_reply(session, 2, {"command": "compute", "answer_from_stdout": True})
                data = r1_state(3, lastCmdResult='[exitCode:0]\n{"city":"Beijing"}\n')
                result = session.handle(data)
                self.assertEqual(result["roleCommandMap"]["11"]["taskAnswer"], '{"city":"Beijing"}')
                self.assertFalse(result["prompt"])
                self.assertFalse(result["executeCmd"])
                self.assertEqual(session.memory.task["submit_mode"], "declared_stdout")
                before = deepcopy(session.memory)
                self.assertEqual(session.handle(data), result)
                self.assertEqual(session.memory, before)
                ensure_valid_response(result)

    def test_regular_stdout_is_not_blindly_submitted(self):
        session = r1_start()
        r1_reply(session, 2, {"command": "cat docs"})
        response = session.handle(r1_state(3, lastCmdResult="[exitCode:0]\nDocumentation, not an answer"))
        self.assertFalse(response["roleCommandMap"])
        self.assertTrue(response["prompt"])
        self.assertIsNone(session.memory.task["candidate"])

    def test_failed_truncated_empty_or_missing_stdout_never_auto_submits(self):
        for raw in ("[TIMEOUT]\n42", "[JUDGER_ERROR]\n42", "[exitCode:1]\n42", "[exitCode:0]\n",
                    "[exitCode:0]\n42\n[TRUNCATED]", "[exitCode:0]\n" + "x" * 20000, "42", None):
            with self.subTest(raw=str(raw)[:80]):
                session = r1_start()
                r1_reply(session, 2, {"command": "compute", "answer_from_stdout": True})
                response = session.handle(r1_state(3, lastCmdResult=raw))
                self.assertFalse(response["roleCommandMap"])
                self.assertIsNone(session.memory.task["candidate"])

    def prepare_fallback(self, candidate="Beijing", source=3, mode="defense"):
        session = r1_start(timeout=8, mode=mode)
        r1_reply(session, 2, {"command": "query city"})
        session.handle(r1_state(3, lastCmdResult="[exitCode:0]\nBeijing"))
        r1_reply(session, 4, {"command": "query remaining fields", "candidate_answer": candidate,
                              "candidate_source_round": source})
        response = session.handle(r1_state(5, lastCmdResult="[exitCode:1]\nno other fields"))
        self.assertTrue(response["prompt"].startswith("FINAL ANSWER REQUIRED"))
        return session

    def test_final_command_instead_of_answer_uses_evidence_fallback(self):
        for mode in ("legacy", "defense"):
            session = self.prepare_fallback(mode=mode)
            response = r1_reply(session, 6, {"command": "one more command"})
            self.assertFalse(response["executeCmd"])
            self.assertEqual(response["roleCommandMap"]["11"]["taskAnswer"], "Beijing")
            self.assertEqual(session.memory.task["submit_mode"], "evidence_fallback")
            self.assertEqual(session.memory.task["last_protocol_error"], "final_answer_required")

    def test_invalid_or_missing_final_reply_also_uses_fallback(self):
        for raw in (None, "bad json", '{"answer":{"city":"Beijing"}}'):
            session = self.prepare_fallback()
            response = session.handle(r1_state(6, llmResp=raw))
            self.assertEqual(response["roleCommandMap"]["11"]["taskAnswer"], "Beijing")

    def test_candidate_must_match_known_successful_source(self):
        for answer, source in (("Moscow", 3), ("Beijing", 2), ("Beijing", 999)):
            session = self.prepare_fallback(answer, source)
            self.assertIsNone(session.memory.task["candidate"])
            response = r1_reply(session, 6, {"command": "again"})
            self.assertFalse(response["roleCommandMap"])
            self.assertEqual(session.memory.task["candidate_reject_reason"], "source_missing_or_output_mismatch")

    def test_fallback_does_not_repeat_an_already_submitted_partial_answer(self):
        session = self.prepare_fallback()
        r1_reply(session, 6, {"command": "again"})
        session.handle(r1_state(7, errors=[{"errorCode": 2}], lastRoundRoleActionResults={"11": True}))
        response = r1_reply(session, 8, {"command": "again"})
        self.assertFalse(response["roleCommandMap"])
        self.assertFalse(response["prompt"])
        self.assertEqual(session.memory.task["dedup_block"], "same_answer_without_new_evidence")

    def test_expired_or_platform_timeout_task_never_submits_candidate(self):
        session = self.prepare_fallback()
        self.assertFalse(session.handle(r1_state(9, llmResp='{"answer":"late"}'))["roleCommandMap"])
        self.assertTrue(session.memory.task["expired"])
        session = self.prepare_fallback()
        response = session.handle(r1_state(6, llmResp='{"answer":"x"}', errors=[{"errorCode": 1}]))
        self.assertFalse(response["roleCommandMap"])
        self.assertFalse(response["prompt"])

    def test_cross_task_cannot_consume_old_reply_or_sources(self):
        session = self.prepare_fallback()
        response = session.handle(r1_state(6, "Different task", llmResp='{"answer":"old"}'))
        self.assertFalse(response["roleCommandMap"])
        self.assertFalse(response["executeCmd"])
        self.assertIsNone(session.memory.task["candidate"])
        self.assertFalse(session.memory.task["sources"])

    def test_gap_discards_candidate_and_late_tool_results(self):
        session = self.prepare_fallback()
        response = session.handle(r1_state(7, llmResp='{"answer":"late"}'))
        self.assertFalse(response["roleCommandMap"])
        self.assertIsNone(session.memory.task["candidate"])
        self.assertFalse(session.memory.task["sources"])
        self.assertIn("A round was missed", response["prompt"])
        session = r1_start()
        r1_reply(session, 2, {"command": "compute", "answer_from_stdout": True})
        self.assertFalse(session.handle(r1_state(4, lastCmdResult="[exitCode:0]\n42"))["roleCommandMap"])
        self.assertFalse(session.memory.task["sources"])

    def test_dead_displaced_or_ended_owner_never_uses_candidate(self):
        for variant in ("dead", "away", "ended"):
            session = self.prepare_fallback()
            data = r1_state(6, llmResp='{"answer":"old"}')
            if variant == "dead":
                data["teamOur"]["roles"][0]["health"] = 0
            elif variant == "away":
                data["teamOur"]["roles"][0]["pos"] = {"x": 30, "y": 30}
            else:
                data["phaseTask"] = ""
                data["teamOur"]["playerTasks"] = []
            response = session.handle(data)
            self.assertFalse(response["executeCmd"])
            self.assertFalse(any(c["action"] == "submitAnswer" for c in response["roleCommandMap"].values()))
            self.assertIsNone(session.memory.task)

    def test_ended_then_identical_text_has_no_old_candidate(self):
        session = self.prepare_fallback()
        session.handle(r1_state(6, ""))
        response = session.handle(r1_state(7, llmResp='{"answer":"stale"}'))
        self.assertIsNone(session.memory.task["candidate"])
        self.assertFalse(session.memory.task["sources"])
        self.assertFalse(response["roleCommandMap"])
        self.assertFalse(session.memory.task["submissions"])

    def test_last_allowed_command_leaves_result_answer_feedback_rounds(self):
        session = r1_start(timeout=6)
        session.handle(r1_state(2, llmResp="invalid"))
        self.assertEqual(r1_reply(session, 3, {"command": "inspect"})["executeCmd"], "inspect")
        self.assertTrue(session.handle(r1_state(4, lastCmdResult="[exitCode:0]\n42"))["prompt"].startswith("FINAL ANSWER REQUIRED"))
        self.assertEqual(r1_reply(session, 5, {"answer": "42"})["roleCommandMap"]["11"]["taskAnswer"], "42")

    def test_unknown_deadline_is_not_invented_and_stdout_path_still_works(self):
        session = GameSession()
        session.handle(r1_state(20))
        self.assertIsNone(session.memory.task["deadline"])
        r1_reply(session, 21, {"command": "compute", "answer_from_stdout": True})
        self.assertEqual(session.handle(r1_state(22, lastCmdResult="[exitCode:0]\n42"))["roleCommandMap"]["11"]["taskAnswer"], "42")

    def test_large_task_and_direct_answer_are_preserved_exactly(self):
        text, answer = "正文" * 40000, "答案" * 40000
        session = GameSession()
        response = session.handle(r1_state(0, text))
        self.assertIn(text, response["prompt"])
        response = r1_reply(session, 1, {"answer": answer}, text)
        self.assertEqual(response["roleCommandMap"]["11"]["taskAnswer"], answer)

    def test_failure_rolls_back_candidate_and_retry_is_safe(self):
        session = r1_start()
        r1_reply(session, 2, {"command": "compute", "answer_from_stdout": True})
        before = deepcopy(session.memory)
        request = r1_state(3, lastCmdResult="[exitCode:0]\n42")
        with patch.object(session_module, "ensure_valid_response", side_effect=RuntimeError("validation failure")):
            with self.assertRaises(RuntimeError):
                session.handle(request)
        self.assertEqual(session.memory, before)
        response = session.handle(request)
        self.assertEqual(response["roleCommandMap"]["11"]["taskAnswer"], "42")

    def test_no_llm_quota_charged_during_task(self):
        session = r1_start()
        for i in range(2, 8):
            session.handle(r1_state(i, llmResp="invalid"))
        self.assertEqual(session.memory.llm_calls_today, 0)


class TaskR1DedupTests(unittest.TestCase):
    def test_permission_error_blocks_immediate_exact_retry(self):
        for code in (126, 127):
            session = r1_start(timeout=30)
            r1_reply(session, 2, {"command": "./script"})
            session.handle(r1_state(3, lastCmdResult=f"[exitCode:{code}]\nfailed"))
            response = r1_reply(session, 4, {"command": "./script"})
            self.assertFalse(response["executeCmd"])
            self.assertEqual(session.memory.task["dedup_block"], "repeated_failed_command")
            self.assertEqual(r1_reply(session, 5, {"command": "python3 script"})["executeCmd"], "python3 script")

    def test_transient_errors_allow_one_retry_then_block(self):
        for raw in ("[TIMEOUT]\nx", "[JUDGER_ERROR]\nx", "[exitCode:1]\nx", "[exitCode:2]\nx", "malformed"):
            session = r1_start(timeout=30)
            r1_reply(session, 2, {"command": "query"})
            session.handle(r1_state(3, lastCmdResult=raw))
            self.assertEqual(r1_reply(session, 4, {"command": "query"})["executeCmd"], "query")
            session.handle(r1_state(5, lastCmdResult=raw))
            self.assertFalse(r1_reply(session, 6, {"command": "query"})["executeCmd"])

    def test_new_successful_evidence_permits_retry(self):
        session = r1_start(timeout=30)
        r1_reply(session, 2, {"command": "./script"})
        session.handle(r1_state(3, lastCmdResult="[exitCode:126]\npermission"))
        r1_reply(session, 4, {"command": "inspect environment"})
        session.handle(r1_state(5, lastCmdResult="[exitCode:0]\npermissions changed"))
        self.assertEqual(r1_reply(session, 6, {"command": "./script"})["executeCmd"], "./script")

    def test_successful_empty_repair_output_unlocks_command_but_is_not_answer(self):
        session = r1_start(timeout=30)
        r1_reply(session, 2, {"command": "./script"})
        session.handle(r1_state(3, lastCmdResult="[exitCode:126]\npermission"))
        r1_reply(session, 4, {"command": "chmod +x script"})
        session.handle(r1_state(5, lastCmdResult="[exitCode:0]\n"))
        self.assertFalse(session.memory.task["sources"])
        self.assertIsNone(session.memory.task["candidate"])
        self.assertEqual(r1_reply(session, 6, {"command": "./script"})["executeCmd"], "./script")

    def test_same_rejected_answer_blocked_then_changed_answer_allowed(self):
        session = r1_start(timeout=30)
        r1_reply(session, 2, {"answer": "wrong"})
        session.handle(r1_state(3, errors=[{"errorCode": 2}], lastRoundRoleActionResults={"11": True}))
        response = r1_reply(session, 4, {"answer": "wrong"})
        self.assertFalse(response["roleCommandMap"])
        self.assertEqual(session.memory.task["dedup_block"], "same_answer_without_new_evidence")
        self.assertEqual(r1_reply(session, 5, {"answer": "improved"})["roleCommandMap"]["11"]["taskAnswer"], "improved")

    def test_legality_false_allows_one_retry_only(self):
        session = r1_start(timeout=30)
        r1_reply(session, 2, {"answer": "answer"})
        session.handle(r1_state(3, lastRoundRoleActionResults={"11": False}))
        self.assertIn("11", r1_reply(session, 4, {"answer": "answer"})["roleCommandMap"])
        session.handle(r1_state(5, lastRoundRoleActionResults={"11": False}))
        self.assertFalse(r1_reply(session, 6, {"answer": "answer"})["roleCommandMap"])

    def test_non_grade_feedback_does_not_claim_answer_verified(self):
        session = r1_start(timeout=30)
        r1_reply(session, 2, {"answer": "answer"})
        session.handle(r1_state(3, lastRoundRoleActionResults={"11": True}))
        record = next(iter(session.memory.task["submissions"].values()))
        self.assertEqual(record["status"], "legal_ungraded")
        self.assertFalse(r1_reply(session, 4, {"answer": "answer"})["roleCommandMap"])


if __name__ == "__main__":
    unittest.main()
