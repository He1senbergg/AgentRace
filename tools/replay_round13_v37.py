"""Historical-input compatibility replay; no recomputed world or score predictions."""
from pathlib import Path
import sys,json,time,copy,concurrent.futures,hashlib,argparse
from v37_support import ROOT,load_source
from audit_round12 import decode_log

def one(path):
    frames,issues=decode_log(path)
    if issues:raise ValueError((str(path),issues))
    mod=load_source('replay_v37',ROOT/'src/main3.py');s=mod.GameSession(origin=1)
    times=[];task_mismatches=[];failures=[];actions=0;full_health_drugs=[];counts={}
    def task_part(r):return {**{k:r[k] for k in ('prompt','executeCmd')},'submits':{a:c for a,c in r['roleCommandMap'].items() if c['action']=='submitAnswer'}}
    active=0
    for n,f in sorted(frames.items()):
        t=time.perf_counter();q=f['request']
        try:
            response=s.handle(copy.deepcopy(q));mod.ensure_valid_response(response);actions+=len(response['roleCommandMap'])
            if q.get('phaseTask'):
                active+=1
                if task_part(response)!=task_part(f['response']):task_mismatches.append(n)
            world=mod.World(q)
            for a,c in response['roleCommandMap'].items():
                if c['action']=='use' and c['name']=='Medicine' and world.characters[a]['health']>=mod.max_health(world.characters[a]):full_health_drugs.append([n,a])
                key=c['action']+':'+c.get('name','');counts[key]=counts.get(key,0)+1
        except Exception as exc:failures.append(dict(round=n,error=repr(exc)))
        times.append(1000*(time.perf_counter()-t))
    report=dict(game=path.parent.name,frames=len(frames),actions=actions,active_task_frames=active,task_mismatches=task_mismatches,
                failures=failures,full_health_medicine=full_health_drugs,p95_ms=sorted(times)[int(.95*(len(times)-1))],max_ms=max(times),
                total_ms=sum(times),commands=counts)
    print('[replay_one] '+json.dumps(report,ensure_ascii=False),flush=True);return report
if __name__=='__main__':
    paths=sorted(ROOT.glob('log/round13/game*/ally*'))
    if not paths:raise SystemExit('[replay_round13] no Round13 print logs provided')
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as ex:rows=list(ex.map(one,paths))
    report=dict(scope='Off-policy historical-input replay. Future world states are original observations, not effects of new actions. No new score/survival inference.',runtime=sys.version,
                source_sha256=hashlib.sha256((ROOT/'src/main3.py').read_bytes()).hexdigest(),games=rows)
    out=ROOT/'runs/v37';out.mkdir(parents=True,exist_ok=True);(out/'replay_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    ok=not any(r['failures'] or r['task_mismatches'] or r['full_health_medicine'] for r in rows)
    print('[replay_round13] complete passed='+str(ok),flush=True);raise SystemExit(0 if ok else 1)
