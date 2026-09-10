import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from test_integration import dense_state

ROOT = Path(__file__).resolve().parents[1]


class LiveHTTPTests(unittest.TestCase):
    def test_dense_http_concurrent_duplicates_and_valid_configuration(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        args = ['--round-origin', '0', '--wall-stone-cost', '2',
                '--weapon-build-name', 'rocket=test-rocket', '--strategy-mode', 'shadow']
        command = ([sys.executable, str(ROOT / 'src/main3.py'), str(port), *args] if os.name == 'nt'
                   else ['bash', str(ROOT / 'run.sh'), str(port), *args])
        env = dict(os.environ, AGENTRACE_PYTHON=sys.executable)

        def post(data):
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            conn = http.client.HTTPConnection(os.environ.get('AGENTRACE_TEST_HOST', '127.0.0.1'),
                                              port, timeout=5)
            started = time.monotonic()
            try:
                conn.request('POST', '/', body, {'Content-Type': 'application/json'})
                reply = conn.getresponse()
                self.assertEqual(reply.status, 200)
                result = json.loads(reply.read())
                self.assertLess(time.monotonic() - started, 5)
                return result
            finally:
                conn.close()

        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(command, cwd=tempfile.gettempdir(), env=env, stdout=log, stderr=log)
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
                build_data = {'roundNo': 0, 'teamOur': {'teamId': 7, 'type': 'challenger', 'goldNum': 75,
                              'roles': [dict(id=1, roleType='worker', pos=dict(x=9, y=8), health=220, backpack=[]),
                                        dict(id=4, roleType='station', pos=dict(x=10, y=10), health=4500, level=3)]}}
                self.assertEqual(post(build_data)['roleCommandMap']['1']['name'], 'test-rocket')
                dense = dense_state()
                self.assertEqual(len(dense['robot']), 1302)
                with ThreadPoolExecutor(max_workers=4) as pool:
                    replies = list(pool.map(post, [dense] * 4))
                self.assertTrue(all(reply == replies[0] for reply in replies))
                self.assertEqual(len(replies[0]['roleCommandMap']), 3)
                self.assertTrue(all(c['action'] == 'attack' for c in replies[0]['roleCommandMap'].values()))
                self.assertEqual(post([]), {'roleCommandMap': {}, 'prompt': '', 'executeCmd': ''})
                dense['roundNo'] = 71
                self.assertEqual(len(post(dense)['roleCommandMap']), 3)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                log.seek(0)
                output = log.read().decode('utf-8', errors='replace')
                self.assertNotIn('Traceback', output)
                self.assertEqual(output.count('[trace_request]'), 3, output)
                self.assertEqual(output.count('[trace_response]'), 3, output)
                shadows = [json.loads(line.split('[shadow_turn] ', 1)[1])
                           for line in output.splitlines() if '[shadow_turn] ' in line]
                self.assertEqual(len(shadows), 3)
                self.assertTrue(all('error' not in row for row in shadows))
                # Exactly one expected malformed request; no silent valid-request fallback.
                self.assertLessEqual(output.count('[process_request]'), 1, output)
            self.assertIsNotNone(process.returncode)
        deadline = time.monotonic() + 2
        while True:
            with socket.socket() as probe:
                probe.settimeout(.2)
                if probe.connect_ex(('127.0.0.1', port)) != 0:
                    break
            if time.monotonic() >= deadline:
                self.fail('listener remained reachable after process exit')
            time.sleep(.02)

    def test_start_repeat_malformed_stop(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        env = dict(os.environ, AGENTRACE_PYTHON=sys.executable)
        command = [sys.executable, str(ROOT / 'src/main3.py'), str(port)]
        process = subprocess.Popen(command, cwd=tempfile.gettempdir(), env=env,
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

    def test_invalid_configuration(self):
        for args in (['--wall-stone-cost', '0'], ['--wall-stone-cost', '-1'],
                     ['--round-origin', '2'], ['--weapon-build-name', 'unknown=x'],
                     ['--weapon-build-name', 'rocket=wall'],
                     ['--weapon-build-name', 'rocket=x', '--weapon-build-name', 'gatling=x'],
                     ['--weapon-build-name', 'rocket=x', '--weapon-build-name', 'rocket=y']):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(ROOT / 'src/main3.py'), '8080', *args],
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b'error:', result.stderr)

    def test_invalid_port(self):
        for port in ('0', '65536', 'bad'):
            result = subprocess.run([sys.executable, str(ROOT / 'src/main3.py'), port],
                                    capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
