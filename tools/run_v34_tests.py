"""Selected current regression suite; deliberately excludes retired legacy modules."""
from pathlib import Path
import json
import sys
import unittest


def run_v34_tests() -> bool:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from src import main3
    main3.print_log = lambda *args, **kwargs: None
    main3.GameSession.trace_turn = lambda *args, **kwargs: None
    suite = unittest.defaultTestLoader.discover(str(root / 'tests_v34'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {'tests': result.testsRun, 'failures': len(result.failures),
               'errors': len(result.errors), 'passed': result.wasSuccessful()}
    print('[run_v34_tests] ' + json.dumps(summary), flush=True)
    return result.wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(0 if run_v34_tests() else 1)
