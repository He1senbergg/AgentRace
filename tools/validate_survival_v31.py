"""Run the V3.1 local acceptance matrix and retain raw output for every command.

Run from any directory with the same Python/Flask environment as the player:
    python -B tools/validate_survival_v31.py --output-dir local_validation_v31
No official robot damage, LLM grading, or 1300-turn survival claim is implied.
"""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def run_check(name: str, arguments: list[str], output: Path, timeout: int) -> dict:
    """Execute in the repo, preserve logs, and distinguish errors from passes."""
    command = [sys.executable, '-B', *arguments]
    started = time.monotonic()
    record = dict(name=name, command=command, cwd=str(ROOT), log=name + '.log', passed=False)
    try:
        with (output / record['log']).open('w', encoding='utf-8') as log:
            process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                     env=dict(os.environ, PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1'),
                                     timeout=timeout, check=False)
        record.update(returncode=process.returncode, passed=process.returncode == 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
    record['seconds'] = round(time.monotonic() - started, 3)
    (output / (name + '.exit.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[run_check] {name}: {'PASS' if record['passed'] else 'FAIL'}; log={output / record['log']}", flush=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'local_validation_v31')
    parser.add_argument('--timeout', type=int, default=600, help='Per-check timeout in seconds.')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Each output directory is an actual run. Never confuse packaged history with a rerun.
    try:
        flask_version = version('Flask')
    except PackageNotFoundError:
        flask_version = None
    summary = dict(complete=False, passed=False, python=sys.version, executable=sys.executable,
                   platform=platform.platform(), flask=flask_version, checks=[],
                   scope='Local regression/HTTP, daytime transitions, economic continuity, and snapshot robustness only; not official survival.',
                   source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((ROOT / 'src').rglob('*.py'))})
    summary_path = output / 'validation_summary.json'

    def save() -> None:
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    reproduction = 'docs/validation_v31/reproduction'
    checks = [
        ('full_suite', ['-m', 'unittest', 'discover', '-s', 'tests', '-v']),
        ('review_assertions', [f'{reproduction}/test_review_regressions.py', str(ROOT), '--json', str(output / 'review_assertions.json')]),
        ('continuous_cases', [f'{reproduction}/review_cases.py', str(ROOT), '--output', str(output / 'continuous_cases.json')]),
        ('initial_maps', ['tools/simulate_survival.py', '--modes', 'survival', '--generated', '8', '--output', str(output / 'initial_maps.json')]),
        ('economic_and_night', ['tools/validate_survival_stress.py', '--output', str(output / 'economic_and_night.json')]),
        ('snapshot_fuzz', ['tools/fuzz_survival_v31.py', '--output', str(output / 'snapshot_fuzz.json')]),
    ]
    save()
    for name, arguments in checks:
        summary['checks'].append(run_check(name, arguments, output, args.timeout))
        save()
    summary['complete'] = True
    summary['passed'] = all(check['passed'] for check in summary['checks'])
    save()
    print(f'[main] Validation summary: {summary_path}', flush=True)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
