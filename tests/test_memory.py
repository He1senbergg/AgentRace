from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import unittest
from unittest.mock import patch

from src import main


def request_at(round_no, **fields):
    return {"roundNo": round_no, "teamOur": {"teamId": 7, "type": "challenger", "roles": []}, **fields}


class MemoryTests(unittest.TestCase):
    def test_callback_integration_and_duplicate_isolation(self):
        calls = []

        def plan(world, memory):
            calls.append(memory.last_round)
            return {"roleCommandMap": {}, "prompt": "中文", "executeCmd": ""}

        session = main.GameSession(plan)
        with patch.object(main, "SESSION", session):
            first = main.callback(request_at(0))
            first["prompt"] = "corrupted"
            self.assertEqual(main.callback(request_at(0))["prompt"], "中文")
        self.assertEqual(calls, [0])
        self.assertEqual(session.memory.phase.day, 1)

    def test_parallel_duplicates_run_planner_once(self):
        calls = []
        session = main.GameSession(lambda w, m: (calls.append(m.last_round), main.empty_response())[1])
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(session.handle, [request_at(0)] * 32))
        self.assertEqual(calls, [0])
        self.assertEqual(responses, [main.empty_response()] * 32)

    def test_transaction_rolls_back_planner_and_validation_failures(self):
        session = main.GameSession()
        session.handle(request_at(0, worldNews={"folkLegends": "第一条"}))
        before = deepcopy(session.memory)

        def fail(world, memory):
            memory.news.clear()
            raise RuntimeError("planner failed")

        for planner in (fail, lambda w, m: {}):
            session.planner = planner
            with self.assertRaises((RuntimeError, ValueError)):
                session.handle(request_at(1))
            self.assertEqual(session.memory, before)
        session.planner = lambda w, m: main.empty_response()
        session.handle(request_at(1))
        self.assertEqual(session.memory.last_round, 1)
        self.assertEqual(len(session.memory.news), 1)

    def test_conflicting_same_round_does_not_commit_and_http_recovers(self):
        session = main.GameSession()
        with patch.object(main, "SESSION", session):
            client = main.app.test_client()
            client.post("/", json=request_at(0))
            before = deepcopy(session.memory)
            with self.assertLogs(main.LOG, level="ERROR"):
                response = client.post("/", json=request_at(0, llmResp="changed"))
            self.assertEqual(response.json, main.empty_response())
            self.assertEqual(session.memory, before)
            self.assertEqual(client.post("/", json=request_at(1)).status_code, 200)
            self.assertEqual(session.memory.last_round, 1)

    def test_history_is_not_current_obstacle_and_news_deduplicates(self):
        session = main.GameSession(origin=1)
        observed = []
        session.planner = lambda w, m: (observed.append(set(w.occupied)), main.empty_response())[1]
        news = {"officialNews": "铁价变化", "folkLegends": "相同线索"}
        session.handle(request_at(1, worldNews=news, teamEnemy={"roles": [
            {"id": 9, "roleType": "worker", "health": 100, "pos": {"x": 8, "y": 9}}]}))
        session.handle(request_at(2, worldNews=news))
        self.assertEqual(len(session.memory.news), 1)
        self.assertIn("9", session.memory.enemy_history)
        self.assertNotIn((8, 9), observed[-1])
        session.handle(request_at(131, worldNews=news))
        self.assertEqual([event["day"] for event in session.memory.news], [1, 2])

    def test_feedback_does_not_infer_success_or_associate_across_gap(self):
        response = {"roleCommandMap": {"10010": {"action": "move", "targetPos": [{"x": 1, "y": 1}]}},
                    "prompt": "", "executeCmd": ""}
        session = main.GameSession(lambda w, m: deepcopy(response))
        observed = {"teamId": 7, "type": "challenger", "roles": [
            {"id": 10010, "roleType": "worker", "pos": {"x": 0, "y": 0}, "health": 220}]}
        session.handle(request_at(0, teamOur=observed))
        session.handle(request_at(1, teamOur=observed, lastRoundRoleActionResults={"10010": False}, llmResp="answer"))
        feedback = session.memory.feedback
        self.assertTrue(feedback["associated"])
        self.assertEqual(feedback["actions"], response["roleCommandMap"])
        self.assertFalse(feedback["results"]["10010"])
        session.handle(request_at(3, teamOur=observed, lastRoundRoleActionResults={"10010": True}))
        self.assertFalse(session.memory.feedback["associated"])
        self.assertEqual(session.memory.feedback["actions"], {})

    def test_identity_change_and_round_regression_reset_history(self):
        for next_request in (request_at(0), request_at(9, teamOur={"teamId": 8, "type": "challenger"}),
                             request_at(9, teamOur={"teamId": 7, "type": "defender"})):
            session = main.GameSession()
            session.handle(request_at(5, worldNews={"folkLegends": "old"}))
            session.handle(next_request)
            self.assertEqual(session.memory.news, [])
            self.assertFalse(session.memory.feedback["associated"])

    def test_missing_invalid_input_and_origin(self):
        session = main.GameSession()
        for data in (None, [], {}, request_at(True), request_at(-1), request_at(1301),
                     request_at(1, teamOur={"teamId": False, "type": "challenger"}),
                     request_at(1, teamOur={"teamId": 1, "type": []})):
            self.assertEqual(session.handle(data), main.empty_response())
            self.assertIsNone(session.memory)
        session.handle(request_at(1))
        self.assertIsNone(session.memory.phase)
        confirmed = main.GameSession(origin=1)
        with self.assertRaises(ValueError):
            confirmed.handle(request_at(0))
        self.assertIsNone(confirmed.memory)
        confirmed.handle(request_at(1300))
        self.assertEqual(confirmed.memory.phase.day, 10)
        inferred = main.GameSession()
        inferred.handle(request_at(0))
        with self.assertRaises(ValueError):
            inferred.handle(request_at(1300))
        self.assertEqual(inferred.memory.last_round, 0)

    def test_unserializable_response_does_not_commit(self):
        session = main.GameSession(lambda w, m: {"roleCommandMap": {}, "prompt": "\ud800", "executeCmd": ""})
        with self.assertRaises(UnicodeEncodeError):
            session.handle(request_at(0))
        self.assertIsNone(session.memory)
        session.planner = lambda w, m: main.empty_response()
        session.handle(request_at(0))
        self.assertEqual(session.memory.last_round, 0)
