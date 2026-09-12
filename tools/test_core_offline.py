"""Run existing non-HTTP assertions against real core exports without Flask.

No Flask mock, HTTP emulation or production-source substitution is used. Copies
of test files change only `from src import main3 as main` to a namespace exporting
the SAME production core objects. HTTP/entrypoint/callback tests are explicitly
excluded and listed; their exclusion is NOT a passing result. On a provisioned
machine prefer: python -B -m unittest discover -s tests -q.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

EXCLUDED_MODULES = {"test_http", "test_protocol", "test_entrypoints"}
EXCLUDED_METHODS = {
    ("test_audit_runtime", "test_http_diagnostic_failure_keeps_committed_response_and_recovers"),
    ("test_audit_runtime", "test_http_error_logging_failure_still_returns_safe_json"),
    ("test_memory", "test_callback_integration_and_duplicate_isolation"),
    ("test_memory", "test_conflicting_same_round_does_not_commit_and_http_recovers"),
    ("test_shadow_instrumentation", "test_port_only_cli_preserves_default_session_and_bind"),
    ("test_equivalence", "test_identical_request_sequences"),
}

CORE_EXPORTS = '''from types import SimpleNamespace
from importlib import import_module
values = {}
for name in ("model", "memory", "actions", "economy", "defense", "task_news", "strategy", "session"):
    module = import_module("src.agentrace." + name)
    values.update({key: value for key, value in vars(module).items() if not key.startswith("_")})
globals().update(values)
main = SimpleNamespace(**values)
'''


def flatten_core_suite(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten_core_suite(item)
        else:
            yield item


def run_core_offline() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    os.environ.pop("AGENTRACE_TASK_TRACE_DIR", None)  # Tests explicitly enable their own temporary paths.
    with tempfile.TemporaryDirectory(prefix="_core_validation_", dir=root) as directory:
        temporary = Path(directory)
        (temporary / "core_offline_exports.py").write_text(CORE_EXPORTS, encoding="utf-8")
        for source in (root / "tests").glob("*.py"):
            text = source.read_text(encoding="utf-8")
            text = text.replace("from src import main3 as main", "from core_offline_exports import main")
            text = text.replace("from src.main3 import ", "from core_offline_exports import ")
            (temporary / source.name).write_text(text, encoding="utf-8")
        sys.path.insert(0, str(temporary))
        # modules such as tests.test_equivalence only import Flask inside HTTP
        # runners, not at import time. All selected tests keep their assertions.
        selected, excluded = [], []
        for path in sorted(temporary.glob("test_*.py")):
            module = importlib.import_module(path.stem)
            for test in flatten_core_suite(unittest.defaultTestLoader.loadTestsFromModule(module)):
                if path.stem in EXCLUDED_MODULES or (path.stem, test._testMethodName) in EXCLUDED_METHODS:
                    excluded.append(test.id())
                else:
                    selected.append(test)
        print("[run_core_offline] Existing assertions with core-import adapter; NOT an HTTP/full-suite run.", flush=True)
        print(f"[run_core_offline] Selected={len(selected)}, excluded={len(excluded)}", flush=True)
        result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(unittest.TestSuite(selected))
        report = {"mode": "real_core_exports_import_adapter_no_http", "python": sys.version,
                  "tests_run": result.testsRun, "failures": [t.id() for t, _ in result.failures],
                  "errors": [t.id() for t, _ in result.errors],
                  "skipped": [{"test": t.id(), "reason": reason} for t, reason in result.skipped],
                  "excluded_http_entry_callback_and_frozen_process_tests": excluded,
                  "passed": result.wasSuccessful()}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_core_offline())
