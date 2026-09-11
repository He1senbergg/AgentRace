"""Frozen V2.2 vs modular implementation on identical precomputed requests."""
from copy import deepcopy
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def request_at(round_no, side='challenger'):
    def role(actor, kind, x, y, hp, **extra):
        return dict(id=actor, roleType=kind, pos=dict(x=x, y=y), health=hp, backpack=[], **extra)
    roles = [role(1, 'worker', 8, 21, 75), role(2, 'worker', 7, 22, 220),
             role(3, 'pioneer', 4, 5, 200), role(9, 'station', 9, 22, 1250, level=1),
             role(10, 'rocket', 9, 20, 1500, level=2), role(11, 'rocket', 8, 22, 1000, level=1),
             role(12, 'rocket', 8, 23, 1000, level=1)]
    roles += [role(20+i, 'wall', 12, 18+i, 400+70*i, level=1) for i in range(8)]
    roles[0]['backpack'] = ['copper'] * (round_no % 20)
    data = dict(roundNo=round_no, teamOur=dict(teamId=7, type=side, roles=roles, goldNum=round_no % 251,
                playerTasks=[dict(taskPosition=dict(x=5, y=5), isValid=True, coldDownRounds=0, timeoutRounds=30)]),
                mapInfo=dict(zones=[dict(neutralType=k, pos=dict(x=x,y=y)) for k,x,y in
                                   [('weaponShop',7,21),('stone',14,23),('copper',6,22),('vendor',6,21),(side+'TaskPoint2',5,5)]]),
                vendorShopList=[dict(name='copper',price=5)],
                weaponShopList=[dict(name=n,price=p) for n,p in [('Medicine',10),('WallFixer',10),('WallUpgradeVoucher1',20),
                     ('WallUpgradeVoucher2',30),('WeaponUpgradeVoucher1',100),('WeaponUpgradeVoucher2',150),('StationUpgradeVoucher1',100)]],
                worldNews=dict(officialNews='资源稳定'), lastRoundRoleActionResults={'1':False})
    offset = round_no % 130
    data['phaseTask'] = 'Read city.txt; return city' if 1 <= offset <= 8 else ''
    if offset == 2:
        data['llmResp'] = '{"command":"cat city.txt","skill":"Read city"}'
    elif offset == 3:
        data['lastCmdResult'] = '[exitCode:0]\nBeijing'
    elif offset == 4:
        data['llmResp'] = '{"answer":"Beijing"}'
    elif offset == 5:
        data['errors'] = [{'errorCode':2}]
    elif offset == 7:
        data['errors'] = [{'errorCode':1}]
    if offset >= 70:
        data['robot'] = [role(100+i, 'smallRobot', 13+i%3, 20+i//3, 40, targetTeam=side) for i in range(6)]
    return data


def cases(full=False):
    rounds = list(range(1301)) if full else [0,1,2,3,4,5,6,7,8,9,69,70,71,72,130,131,132,200,260,261,262,330,331,390,391,392,1300]
    result = []
    for mode in ('legacy','shadow','defense'):
        for origin in (0,1):
            seq = []
            for side in ('challenger','defender'):
                seq += [request_at(r,side) for r in rounds if r >= origin]
            seq += [deepcopy(seq[-1]), dict(deepcopy(seq[-1]), llmResp='conflicting'), request_at(1), None, {}, request_at(2)]
            result.append(dict(mode=mode, origin=origin, requests=seq))
        result.append(dict(mode=mode, http=True, requests=[
            dict(body=json.dumps(request_at(1)),content_type='application/json'),
            dict(body=json.dumps(request_at(1)),content_type='application/json'),
            dict(body='{"roundNo":1,"roundNo":2}',content_type='application/json'),
            dict(body='[]',content_type='application/json'), dict(body='{',content_type='application/json'),
            dict(body='{}',content_type='text/plain'),dict(body=json.dumps(request_at(2)),content_type='application/json')]))
    for mode in ('legacy', 'shadow'):
        result.append(dict(mode=mode, fault_at={'1':'planner','3':'validation'},
                           requests=[request_at(r) for r in [1,2,2,3,3,4]]))
    if full:
        for case in result:
            case['compact_state'] = True
    return result


def run_impl(name, payload):
    result = subprocess.run([sys.executable,'-B','-m','tests.equivalence_runner',name], input=payload,
                            text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=ROOT, timeout=240, env=dict(os.environ, PYTHONHASHSEED='0'))
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])
    return json.loads(result.stdout)


class EquivalenceTests(unittest.TestCase):
    def test_package_dependencies_are_acyclic_and_downward(self):
        allowed = {
            'model': set(), 'memory': {'model'}, 'actions': {'model'}, 'economy': {'model'},
            'defense': {'model', 'economy'}, 'task_news': {'model', 'actions', 'economy'},
            'strategy': {'model', 'memory', 'actions', 'economy', 'defense', 'task_news'},
            'session': {'model', 'memory', 'actions', 'task_news', 'strategy'},
        }
        edges = {}
        for name, dependencies in allowed.items():
            tree = ast.parse((ROOT/'src/agentrace'/f'{name}.py').read_text(encoding='utf-8'))
            actual = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn('main3', node.module or '')
                    if node.level:
                        self.assertEqual(node.level, 1)
                        actual.add(node.module)
                elif isinstance(node, ast.Import):
                    self.assertTrue(all('main3' not in a.name for a in node.names))
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {'exec', 'eval', '__import__'})
            self.assertTrue(actual <= dependencies, (name, actual))
            edges[name] = actual
        def visit(name, ancestors):
            self.assertNotIn(name, ancestors)
            for dependency in edges[name]:
                visit(dependency, ancestors | {name})
        for name in edges:
            visit(name, set())

    def test_all_existing_definition_bodies_and_constants_unchanged(self):
        old = ast.parse((ROOT/'tests/fixtures/v22_baseline.py').read_text(encoding='utf-8'))
        definitions = {}
        assignments = {}
        for path in [ROOT/'src/main3.py', *sorted((ROOT/'src/agentrace').glob('*.py'))]:
            for node in ast.parse(path.read_text(encoding='utf-8')).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    self.assertNotIn(node.name, definitions)
                    definitions[node.name] = node
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assignments.setdefault(target.id, []).append(node.value)
        for node in old.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                self.assertEqual(ast.dump(node), ast.dump(definitions[node.name]), node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper() and target.id != 'LOG':
                        self.assertEqual([ast.dump(node.value)], [ast.dump(v) for v in assignments[target.id]], target.id)

    def test_frozen_digest(self):
        fixture = ROOT/'tests/fixtures/v22_baseline.py'
        expected = fixture.with_suffix('.sha256').read_text(encoding='ascii').strip()
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), expected)

    def test_identical_request_sequences(self):
        payload = json.dumps(cases(os.environ.get('AGENTRACE_FULL_EQ') == '1'), ensure_ascii=True)
        old, new = run_impl('baseline',payload), run_impl('modular',payload)
        self.assertEqual(len(old), len(new))
        for c, (left,right) in enumerate(zip(old,new)):
            self.assertEqual(len(left),len(right))
            for r,(a,b) in enumerate(zip(left,right)):
                self.assertEqual(a,b, f'case={c} request={r}')


if __name__ == '__main__':
    unittest.main()
