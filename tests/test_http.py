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
    def test_task_repair_stdout_submission_and_duplicate_delivery(self):
        from test_task_protocol_r1 import r1_state

        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]

        def post(data):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            started = time.monotonic()
            try:
                conn.request('POST', '/', json.dumps(data).encode('utf-8'), {'Content-Type': 'application/json'})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                result = json.loads(response.read())
                self.assertEqual(set(result), {'roleCommandMap', 'prompt', 'executeCmd'})
                self.assertLess(time.monotonic() - started, 5)
                return result
            finally:
                conn.close()

        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(
                [sys.executable, str(ROOT / 'src/main3.py'), str(port)],
                cwd=tempfile.gettempdir(), stdout=log, stderr=log,
                env=dict(os.environ, AGENTRACE_TASK_TRACE_DIR=''),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
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
                self.assertEqual(post(r1_state(0, ''))['roleCommandMap']['11']['action'], 'acceptTask')
                self.assertTrue(post(r1_state(1))['prompt'])
                bad = post(r1_state(2, llmResp='{"answer":{"city":"PRIVATE_CITY"}}'))
                self.assertIn('answer_must_be_string', bad['prompt'])
                self.assertFalse(bad['roleCommandMap'])
                repaired = post(r1_state(3, llmResp=json.dumps(
                    {'command': 'PRIVATE_COMPUTE', 'answer_from_stdout': True})))
                self.assertEqual(repaired['executeCmd'], 'PRIVATE_COMPUTE')
                data = r1_state(4, lastCmdResult='[exitCode:0]\n{"city":"PRIVATE_CITY"}\n')
                with ThreadPoolExecutor(max_workers=4) as pool:
                    replies = list(pool.map(post, [data] * 4))
                self.assertTrue(all(reply == replies[0] for reply in replies))
                self.assertEqual(replies[0]['roleCommandMap']['11']['taskAnswer'], '{"city":"PRIVATE_CITY"}')
                self.assertFalse(replies[0]['prompt'])
                post(r1_state(5, errors=[{'errorCode': 2}], lastRoundRoleActionResults={'11': True}))
                duplicate = post(r1_state(6, llmResp=json.dumps({'answer': '{"city":"PRIVATE_CITY"}'})))
                self.assertFalse(duplicate['roleCommandMap'])
                improved = post(r1_state(7, llmResp=json.dumps({'answer': '{"city":"PRIVATE_CORRECTION"}'})))
                self.assertEqual(improved['roleCommandMap']['11']['taskAnswer'], '{"city":"PRIVATE_CORRECTION"}')
                self.assertFalse(post(r1_state(8, '', timeout=100))['prompt'])
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
            for marker in ('PRIVATE_CITY', 'PRIVATE_COMPUTE', 'PRIVATE_CORRECTION'):
                self.assertNotIn(marker, output)
            rows = [json.loads(line.split('[turn] ', 1)[1]) for line in output.splitlines() if '[turn] ' in line]
            submitted = [row for row in rows if row['round'] == 4]
            self.assertEqual(len(submitted), 1)
            self.assertEqual(submitted[0]['task']['submit_mode'], 'declared_stdout')

    def test_dense_http_concurrent_duplicates_with_default_configuration(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        command = ([sys.executable, str(ROOT / 'src/main3.py'), str(port)] if os.name == 'nt'
                   else ['bash', str(ROOT / 'run.sh'), str(port)])
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
                self.assertEqual(post(build_data)['roleCommandMap']['1']['name'], 'rocket')
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
                self.assertTrue(all(row['strategy_mode'] == 'defense' for row in shadows))
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

    def test_removed_options_and_extra_arguments_are_rejected(self):
        for args in (['--strategy-mode', 'defense'], ['--wall-stone-cost', '1'],
                     ['--round-origin', '0'], ['--weapon-build-name', 'rocket=rocket'], ['8081']):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(ROOT / 'src/main3.py'), '8080', *args],
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b'unrecognized arguments:', result.stderr)

    def test_invalid_port(self):
        for args in ([], ['-1'], ['0'], ['65536'], ['bad']):
            result = subprocess.run([sys.executable, str(ROOT / 'src/main3.py'), *args],
                                    capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
