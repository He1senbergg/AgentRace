import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LiveHTTPTests(unittest.TestCase):
    def test_start_repeat_malformed_stop(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        env = dict(os.environ, AGENTRACE_PYTHON=sys.executable)
        process = subprocess.Popen(['bash', str(ROOT / 'run.sh'), str(port)], cwd='/tmp', env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while True:
                self.assertIsNone(process.poll(), 'server exited before startup')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        self.fail('startup exceeded five seconds')
                    time.sleep(.02)
            first = json.dumps({'roundNo': 0, 'teamOur': {'teamId': 7, 'type': 'challenger'},
                                'worldNews': {'folkLegends': '保留线索'}}, ensure_ascii=False).encode('utf-8')
            second = json.dumps({'roundNo': 1, 'teamOur': {'teamId': 7, 'type': 'challenger'}})
            for body in (first, first, '{', second):
                start = time.monotonic()
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
                try:
                    conn.request('POST', '/', body, {'Content-Type': 'application/json'})
                    response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read()), {'roleCommandMap': {}, 'prompt': '', 'executeCmd': ''})
                finally:
                    conn.close()
                self.assertLess(time.monotonic() - start, 5)
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        self.assertIsNotNone(process.returncode)

    def test_invalid_port(self):
        for port in ('0', '65536', 'bad'):
            result = subprocess.run([sys.executable, str(ROOT / 'src/main.py'), port],
                                    capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
