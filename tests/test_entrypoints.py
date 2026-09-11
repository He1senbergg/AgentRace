"""Real process tests for the unchanged multi-file deployment entry contract."""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from tests.test_equivalence import ROOT, request_at, run_impl


def bash_command():
    if os.name == 'nt':
        for path in [Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Git/bin/bash.exe',
                     Path(os.environ.get('LOCALAPPDATA', 'C:/Users') )/'Programs/Git/bin/bash.exe']:
            if path.exists():
                return str(path)
        return None  # WSL bash cannot directly execute this Windows Python runtime.
    return shutil.which('bash')


class EntrypointTests(unittest.TestCase):
    def check_http(self, bash=False):
        shell = bash_command() if bash else None
        if bash and not shell:
            self.skipTest('POSIX bash with compatible Python not installed')
        requests = [dict(body=json.dumps(request_at(r)), content_type='application/json') for r in (1, 2, 2, 70, 71)]
        requests += [dict(body='{', content_type='application/json'), dict(body='{}', content_type='text/plain')]
        expected = run_impl('baseline', json.dumps([dict(mode='shadow', http=True, requests=requests)]))[0]
        with tempfile.TemporaryDirectory() as directory:
            deployed = Path(directory)
            shutil.copytree(ROOT/'src', deployed/'src', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(ROOT/'run.sh', deployed/'run.sh')
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            command = [shell, str(deployed/'run.sh'), str(port)] if bash else [sys.executable, str(deployed/'src/main3.py'), str(port)]
            with tempfile.TemporaryFile() as log:
                process = subprocess.Popen(command, cwd=ROOT.parent, stdout=log, stderr=log,
                                           env=dict(os.environ, AGENTRACE_PYTHON=sys.executable, PYTHONHASHSEED='0'),
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                try:
                    deadline = time.monotonic()+10
                    while True:
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read().decode('utf-8',errors='replace')[-3000:])
                        try:
                            with socket.create_connection(('127.0.0.1',port),timeout=0.2):
                                break
                        except OSError:
                            if time.monotonic()>deadline:
                                self.fail('HTTP server startup timeout')
                            time.sleep(0.03)
                    for req, reference in zip(requests,expected):
                        connection = http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                        try:
                            connection.request('POST','/',body=req['body'].encode('utf-8'),headers={'Content-Type':req['content_type']})
                            response = connection.getresponse()
                            self.assertEqual(response.status,reference['status'])
                            self.assertEqual(response.read().decode('utf-8'),reference['body'])
                        finally:
                            connection.close()
                finally:
                    if process.poll() is None:
                        if os.name == 'nt':
                            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                        else:
                            process.terminate()
                        process.wait(timeout=10)

    def test_direct_entry_http_from_deployment_closure(self):
        self.check_http()

    def test_unmodified_run_sh_http_from_deployment_closure(self):
        self.check_http(bash=True)

    def test_package_import(self):
        result = subprocess.run([sys.executable,'-B','-c','from src import main3; assert main3.SESSION.strategy_mode == "shadow"; assert main3.app'],
                                cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_existing_replay_cli_relative_paths_outside_repository(self):
        log = ROOT/'log/Versus/round4/game12/ally_RedSide_263.log'
        values=[]
        for source in (ROOT/'tests/fixtures/v22_baseline.py', ROOT/'src/main3.py'):
            result = subprocess.run([sys.executable,'-B',str(ROOT/'tools/replay_day.py'),
                                     os.path.relpath(log,ROOT.parent),'--source',os.path.relpath(source,ROOT.parent)],
                                    cwd=ROOT.parent,capture_output=True,text=True,encoding='utf-8',timeout=60)
            self.assertEqual(result.returncode,0,result.stderr[-3000:])
            values.append(json.loads(result.stdout))
        self.assertEqual(values[0],values[1])
