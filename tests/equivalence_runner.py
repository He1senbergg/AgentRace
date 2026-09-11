"""Isolated runner. Requests arrive unchanged on stdin; output is field snapshots."""
import dataclasses
import hashlib
import json
import logging
import sys


def snapshot(value):
    if dataclasses.is_dataclass(value):
        return {f.name: snapshot(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {'mapping': sorted([[snapshot(k), snapshot(v)] for k, v in value.items()],
                                  key=lambda row: json.dumps(row[0], sort_keys=True))}
    if isinstance(value, (set, frozenset)):
        return {'set': sorted([snapshot(v) for v in value], key=lambda v: json.dumps(v, sort_keys=True))}
    if isinstance(value, (tuple, list)):
        return [snapshot(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(type(value).__name__)


def main():
    if sys.argv[1] == 'baseline':
        from .fixtures import v22_baseline as player
    else:
        from src import main3 as player
    logging.disable(logging.CRITICAL)
    cases = json.load(sys.stdin)
    output = []
    for case in cases:
        session = player.GameSession(strategy_mode=case['mode'], origin=case.get('origin'))
        player.SESSION = session
        client = player.app.test_client()
        rows = []
        for index, request in enumerate(case['requests']):
            saved = session.planner
            fault = case.get('fault_at', {}).get(str(index))
            if fault == 'planner':
                def failed(world, memory):
                    memory.news.clear()
                    raise RuntimeError('characterization failure')
                session.planner = failed
            elif fault == 'validation':
                session.planner = lambda w, m: {'invalid': True}
            if case.get('http'):
                response = client.post('/', data=request['body'], content_type=request['content_type'])
                result = {'status': response.status_code, 'body': response.get_data(as_text=True)}
            else:
                try:
                    result = {'response': session.handle(request)}
                except Exception as exc:
                    result = {'error': type(exc).__name__, 'message': str(exc)}
            state = snapshot(session.memory)
            if case.get('compact_state'):
                # Hash every normalized field; keep Responses themselves verbatim.
                state = hashlib.sha256(json.dumps(state,sort_keys=True,ensure_ascii=True,
                                                  separators=(',',':')).encode('ascii')).hexdigest()
            result['state'] = state
            result['cached_response'] = snapshot(session.response)
            result['fingerprint'] = session.fingerprint.hex() if session.fingerprint else None
            rows.append(result)
            session.planner = saved
        output.append(rows)
    json.dump(output, sys.stdout, ensure_ascii=True, allow_nan=False)


if __name__ == '__main__':
    main()
