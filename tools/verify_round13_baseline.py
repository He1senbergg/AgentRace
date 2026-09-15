"""Reproduce V3.6 decisions before selected Round13 regression snapshots.

Reads only user-provided print logs. This is not a game simulator.
"""
from pathlib import Path
import concurrent.futures
import copy
import hashlib
import json
from audit_round12 import decode_log
from v37_support import ROOT, load_source


def verify_one(job):
    game, stop = job
    paths = list((ROOT / 'log' / 'round13' / game).glob('ally*'))
    if len(paths) != 1:
        raise ValueError(f'{game}: expected one local ally print log')
    frames, issues = decode_log(paths[0])
    if issues:
        raise ValueError(f'{game}: incomplete or corrupt replay data')
    mod = load_source('baseline_v36_reproduction', ROOT / 'tests/tests_v37/fixtures/baseline_v36.py')
    session = mod.GameSession(origin=1)
    mismatches = []
    checked = 0
    for round_no, frame in sorted(frames.items()):
        if round_no > stop:
            break
        out = session.handle(copy.deepcopy(frame['request']))
        checked += 1
        if out != frame['response']:
            mismatches.append(round_no)
    if checked != stop:
        raise ValueError(f'{game}: expected rounds 1..{stop}, checked {checked}')
    return dict(game=game, checked=checked, mismatches=mismatches)


def verify_round13_baseline():
    fixtures = json.loads((ROOT / 'tests/tests_v37/fixtures/round13_cases.json').read_text(encoding='utf-8'))
    jobs = [(game, max(map(int, entries))) for game, entries in fixtures['games'].items()]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(verify_one, jobs))
    report = dict(scope='Exact original-response reproduction, not new-policy outcomes.',
                  baseline_sha256=hashlib.sha256((ROOT / 'tests/tests_v37/fixtures/baseline_v36.py').read_bytes()).hexdigest(),
                  checked=sum(x['checked'] for x in rows), games=rows,
                  passed=not any(x['mismatches'] for x in rows))
    out = ROOT / 'runs/v37/baseline_reproduction.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[verify_round13_baseline] ' + json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(verify_round13_baseline())
