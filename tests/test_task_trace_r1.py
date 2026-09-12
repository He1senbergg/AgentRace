"""Private trace IO isolation and ordinary-log privacy; REAL local files only."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.agentrace import task_trace
from src.agentrace.session import GameSession, LOG
from test_task_protocol_r1 import r1_state, r1_reply


class TaskR1TraceTests(unittest.TestCase):
    def test_disabled_by_default_does_not_touch_files(self):
        with patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": ""}):
            with patch.object(task_trace.os, "open", side_effect=AssertionError("must not open")):
                self.assertTrue(GameSession().handle(r1_state())["prompt"])

    def test_enabled_captures_raw_input_and_output_and_no_duplicate_delivery(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": directory}):
            session = GameSession()
            data = r1_state(0, "PRIVATE_TASK_MARKER")
            expected = session.handle(data)
            session.handle(data)
            r1_reply(session, 1, {"answer": "PRIVATE_ANSWER"}, "PRIVATE_TASK_MARKER")
            files = list(Path(directory).glob("*.tasktrace.jsonl"))
            self.assertEqual(len(files), 1)
            rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["response"], expected)
            self.assertEqual(rows[0]["phaseTask"], "PRIVATE_TASK_MARKER")
            self.assertEqual(rows[1]["response"]["roleCommandMap"]["11"]["taskAnswer"], "PRIVATE_ANSWER")
            if os.name != "nt":
                self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)

    def test_task_end_feedback_is_recorded_without_invented_score(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": directory}):
            session = GameSession()
            session.handle(r1_state())
            session.handle(r1_state(1, "", errors=[{"errorCode": 1}]))
            rows = [json.loads(line) for line in next(Path(directory).glob("*.jsonl")).read_text().splitlines()]
            self.assertEqual(rows[-1]["errors"], [{"errorCode": 1}])
            self.assertNotIn("score", rows[-1])

    def test_ordinary_logs_never_include_raw_task_answer_or_command(self):
        with patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": ""}):
            session = GameSession()
            with self.assertLogs(LOG, level="INFO") as logs:
                session.handle(r1_state(0, "PRIVATE_TASK"))
                r1_reply(session, 1, {"command": "PRIVATE_CMD", "answer_from_stdout": True}, "PRIVATE_TASK")
                session.handle(r1_state(2, "PRIVATE_TASK", lastCmdResult="[exitCode:0]\nPRIVATE_ANSWER"))
            output = "\n".join(logs.output)
            for secret in ("PRIVATE_TASK", "PRIVATE_CMD", "PRIVATE_ANSWER"):
                self.assertNotIn(secret, output)
            rows = [json.loads(line.split("[turn] ", 1)[1]) for line in logs.output if "[turn] " in line]
            self.assertTrue(rows[-1]["task"]["candidate_available"])
            self.assertEqual(rows[-1]["task"]["submit_mode"], "declared_stdout")

    def test_io_and_logging_failures_do_not_change_response(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": directory}):
            with patch.object(task_trace.os, "open", side_effect=OSError("PRIVATE_PATH")):
                with self.assertLogs(LOG, level="WARNING") as logs:
                    session = GameSession()
                    response = session.handle(r1_state())
                    self.assertTrue(response["prompt"])
                    self.assertEqual(session.handle(r1_state()), response)
                self.assertNotIn("PRIVATE_PATH", "\n".join(logs.output))
                with patch.object(LOG, "warning", side_effect=OSError("log blocked")):
                    self.assertTrue(GameSession().handle(r1_state())["prompt"])

    def test_large_record_has_explicit_omission_marker(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": directory}):
            with patch.object(task_trace, "TASK_TRACE_RECORD_LIMIT", 100):
                GameSession().handle(r1_state())
            row = json.loads(next(Path(directory).glob("*.jsonl")).read_text())
            self.assertTrue(row["payload_omitted"])
            self.assertIn("original_bytes", row)

    def test_rotation_is_bounded_and_all_files_remain_json_lines(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": directory}):
            with patch.object(task_trace, "TASK_TRACE_FILE_LIMIT", 4000):
                session = GameSession()
                for i in range(12):
                    session.handle(r1_state(i, llmResp="invalid"))
            files = list(Path(directory).glob("*.tasktrace.jsonl*"))
            self.assertLessEqual(len(files), 4)
            self.assertGreater(len(files), 1)
            for file in files:
                for line in file.read_text(encoding="utf-8").splitlines():
                    self.assertIsInstance(json.loads(line), dict)

    @unittest.skipIf(os.name == "nt", "POSIX symlink test")
    def test_symlink_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AGENTRACE_TASK_TRACE_DIR": directory}):
            outside = Path(directory) / "outside.txt"
            outside.write_text("DO_NOT_TOUCH")
            link = Path(directory) / ("task-" + str(os.getpid()) + ".tasktrace.jsonl")
            link.symlink_to(outside)
            with self.assertLogs(LOG, level="WARNING"):
                self.assertTrue(GameSession().handle(r1_state())["prompt"])
            self.assertEqual(outside.read_text(), "DO_NOT_TOUCH")


if __name__ == "__main__":
    unittest.main()
