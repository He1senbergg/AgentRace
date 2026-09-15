"""Deterministic adversarial snapshots and unchanged-code audit (local only)."""
from pathlib import Path
import sys,json,copy,random,ast,hashlib,time
from v37_support import ROOT,load_source
mod=load_source('invariants_v37',ROOT/'src/main3.py')
oldpath=ROOT/'tests/tests_v38/fixtures/baseline_v37.py'
old=load_source('invariants_v36',oldpath)

def kernels(text):
    tree=ast.parse(text)
    names={'TaskPlanner','CombatPlanner','ActionValidator','GameSession','GameMemory','AgentHTTPHandler',
           'deployment_repair_command','heritage_query_command','make_task_context','render_task_prompt','canonical_task_answer',
           'parse_deployment_spec','decode_task_reply','save_task_candidate','observe_task_command'}
    return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names}

def run_invariants():
    before=kernels(oldpath.read_text());after=kernels((ROOT/'src/main3.py').read_text())
    assert before==after,'an out-of-scope kernel changed'
    fixture=json.loads((ROOT/'tests/tests_v37/fixtures/round13_cases.json').read_text())
    entries=[entry for game in fixture['games'].values() for entry in game.values()]
    rng=random.Random(38014);counts=0;max_ms=0;failures=[]
    for i in range(800):
        q=copy.deepcopy(entries[i%len(entries)]['request']);q['teamOur']['goldNum']=rng.choice([0,9,10,19,20,24,25,99,100,149,150,300])
        roles=q['teamOur']['roles']
        for r in roles:
            if r['roleType'] in ('worker','pioneer'):
                maximum=220 if r['roleType']=='worker' else 200
                r['health']=rng.choice([1,30,80,maximum-1,maximum])
                r['backpack']=rng.choice([[],['Medicine'],['WallFixer'],['Medicine','WallFixer'],['WallUpgradeVoucher1'],['StationUpgradeVoucher2'],['copper']*4])
            elif r['roleType']=='wall':r['health']=rng.choice([1,85,300,500+500*r['level']])
        q['lastRoundRoleActionResults']={};q['errors']=[]
        s=mod.GameSession(origin=1);t=time.perf_counter()
        try:
            out=s.handle(q);mod.ensure_valid_response(out)
            assert s.handle(copy.deepcopy(q))==out,'duplicate changed'
            world=mod.World(q);moves=[];controllers=[];spend=0;prices={p['name']:p['price'] for p in q['weaponShopList']}
            for a,c in out['roleCommandMap'].items():
                if c['action']=='buy':spend+=prices[c['name']]*c['num']
                if c['action']=='build' and c['name']!='wall':spend+=25
                if c['action']=='move':moves.append(tuple(c['targetPos'][0].values()))
                if c['action']=='attack':controllers.append(c['controllerId'])
                if c['action']=='use' and c['name']=='Medicine':
                    assert world.characters[a]['health']<mod.max_health(world.characters[a]),'full-health medicine'
            assert spend<=q['teamOur']['goldNum'],'overspend'
            assert len(set(moves))==len(moves),'colliding moves'
            assert len(set(controllers))==len(controllers),'controller used twice'
            assert not set(controllers)&set(out['roleCommandMap']),'controller also issued independent action'
            if not s.memory.phase.is_day:assert not any(c['action']=='build' for c in out['roleCommandMap'].values())
            counts+=1
        except Exception as exc:failures.append(dict(index=i,error=repr(exc)))
        max_ms=max(max_ms,1000*(time.perf_counter()-t))
    result=dict(runtime=sys.version,source_sha256=hashlib.sha256((ROOT/'src/main3.py').read_bytes()).hexdigest(),
                unchanged_kernels=list(before),mutation_cases=800,passed=counts,failures=failures,max_ms=max_ms,
                scope='Fixed-seed mutated actual snapshots, clean memory per case. Cash/legality/idempotency/health guards, not win-rate.')
    (ROOT/'runs/v38/invariants.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('[run_invariants] '+json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if not failures else 1
if __name__=='__main__':raise SystemExit(run_invariants())
