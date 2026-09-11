"""Local MATCH2 chunk decoder. Verify complete chunks, byte length and SHA-256."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib


def decode(path):
    groups = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.startswith('MATCH2 '):
            continue
        _, run, seq, event, turn, kind, part, length, digest, payload = line.split()
        index, count = map(int, part.split('/'))
        key = run, event
        metadata = turn, kind, count, int(length), digest
        record = groups.setdefault(key, (metadata, {}))
        if record[0] != metadata or index in record[1] or not 0 <= index < count:
            raise ValueError(f'inconsistent/duplicate MATCH2 chunk: {key}')
        record[1][index] = payload
    result = []
    for (run, event), ((turn, kind, count, length, digest), parts) in groups.items():
        if set(parts) != set(range(count)):
            raise ValueError(f'incomplete MATCH2 event: {run}/{event}')
        encoded = ''.join(parts[i] for i in range(count))
        raw = zlib.decompress(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if len(raw) != length or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f'MATCH2 integrity failure: {run}/{event}')
        result.append(dict(run=run, event=event, round=None if turn == '-' else int(turn),
                           kind=kind, data=json.loads(raw)))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log')
    args = parser.parse_args()
    print(json.dumps(decode(args.log), ensure_ascii=False))
