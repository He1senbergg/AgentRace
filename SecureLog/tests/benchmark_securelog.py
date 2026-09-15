# -*- coding: utf-8 -*-
"""Local microbenchmark. Does not measure actual platform stdout or game response time."""
import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import securelog_runtime as rt
import log_tool as tool


def benchmark(n: int, e: int, repetitions: int = 30) -> dict:
    cases = {
        'strategy_2KiB_compressible': b'{"budget":300,"wall_goal":14,"role":"worker"}' * 48,
        'replay_fragment_1500_random_ascii': __import__('base64').b64encode(os.urandom(1125)),
        'random_16KiB': os.urandom(16384),
        'random_64KiB': os.urandom(65536),
    }
    results = {}
    for name, raw in cases.items():
        count = {'lines': 0, 'chars': 0}
        def sink(line):
            count['lines'] += 1
            count['chars'] += len(line) + 1
        logger = rt._SLSecureLogger(n, e, sink)
        start = time.perf_counter()
        if not logger.emit_bytes(raw):
            raise RuntimeError('encryption failed')
        first_ms = 1000 * (time.perf_counter() - start)
        times = []
        for _ in range(repetitions):
            start = time.perf_counter()
            if not logger.emit_bytes(raw):
                raise RuntimeError('encryption failed')
            times.append(1000 * (time.perf_counter() - start))
        ordered = sorted(times)
        results[name] = {
            'raw_bytes': len(raw), 'repetitions': repetitions,
            'first_record_ms_including_key_wrap': round(first_ms, 3),
            'steady_median_ms': round(statistics.median(times), 3),
            'steady_p95_ms': round(ordered[int((len(ordered)-1)*.95)], 3),
            'steady_max_ms': round(max(times), 3),
            'mean_output_lines': count['lines']/(repetitions+1),
            'mean_output_chars': count['chars']/(repetitions+1),
        }
    return {'rsa_bits': n.bit_length(), 'results': results,
            'sink': 'in-memory counting function; NOT platform print/flush',
            'official_platform_measured': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='本地性能测试，不代表比赛平台性能')
    parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=30)
    args = parser.parse_args()
    n, e = tool.load_public(args.public)
    print('[benchmark] ' + json.dumps(benchmark(n, e, args.repetitions), ensure_ascii=False, indent=2), flush=True)
