"""Opt-in LOCAL task audit, disabled unless AGENTRACE_TASK_TRACE_DIR is set.

Contains raw task/prompt/answer/tool text and may contain internal information.
Use only in an approved private directory. Nothing is uploaded. Ordinary logs
remain metadata-only. Bounded rotation and failure isolation are not a hard
real-time guarantee for a blocked filesystem; keep this off in that environment.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import stat
import threading
import time

TASK_TRACE_FILE_LIMIT = 16 * 1024 * 1024
TASK_TRACE_RECORD_LIMIT = 2 * 1024 * 1024
TASK_TRACE_LOCK = threading.Lock()


def write_task_trace(data: dict, response: dict, memory, session_tag: str) -> None:
    """Best-effort diagnostics only; never change a committed game response."""
    directory = os.environ.get("AGENTRACE_TASK_TRACE_DIR", "")
    if not directory or memory is None:
        return
    active = isinstance(data.get("phaseTask"), str) and bool(data["phaseTask"])
    if not active and memory.task_diagnostics.get("task_end") is None:
        return
    try:
        root = Path(directory).expanduser()
        if root.is_symlink():
            raise ValueError("trace directory must not be a symlink")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        task = memory.task or {}
        event = {"version": "task-r1", "timestamp_unix": time.time(),
                 "session": session_tag, "round": memory.last_round,
                 "side": memory.identity[1], "origin": memory.origin,
                 "task_started_round": task.get("started_round"),
                 "phaseTask": data.get("phaseTask"), "llmResp": data.get("llmResp"),
                 "lastCmdResult": data.get("lastCmdResult"), "errors": data.get("errors"),
                 "lastRoundRoleActionResults": data.get("lastRoundRoleActionResults"),
                 "response": response, "stage": task.get("prompt_stage"),
                 "protocol_error": task.get("last_protocol_error"), "dedup_block": task.get("dedup_block"),
                 "candidate": task.get("candidate"), "submit_mode": task.get("submit_mode"),
                 "deadline": task.get("deadline"), "submission_block": task.get("submission_block")}
        payload = (json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > TASK_TRACE_RECORD_LIMIT:
            payload = (json.dumps({"version": "task-r1", "session": session_tag, "round": memory.last_round,
                                   "payload_omitted": True, "reason": "record_byte_limit",
                                   "original_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}) + "\n").encode("utf-8")
        path = root / ("task-" + str(os.getpid()) + ".tasktrace.jsonl")
        with TASK_TRACE_LOCK:
            if path.is_symlink():
                raise ValueError("trace file must not be a symlink")
            if path.exists() and path.stat().st_size + len(payload) > TASK_TRACE_FILE_LIMIT:
                for index in (3, 2, 1):
                    previous = root / (path.name + "." + str(index))
                    following = root / (path.name + "." + str(index + 1))
                    if previous.exists():
                        if index == 3:
                            previous.unlink()
                        else:
                            os.replace(previous, following)
                os.replace(path, root / (path.name + ".1"))
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(path, flags, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ValueError("trace must be a regular local file")
                with os.fdopen(descriptor, "ab") as stream:
                    descriptor = None
                    stream.write(payload)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
    except Exception as exc:
        try:
            logging.getLogger("src.main3").warning("[write_task_trace] 本地任务审计未写入: %s", type(exc).__name__)
        except Exception:
            pass
