"""Off-policy compatibility only: does not compute candidate match scores."""
from pathlib import Path
import pickle,sys,importlib.util,copy,json,time,concurrent.futures,hashlib,statistics
ROOT=Path(__file__).resolve().parents[1]
from audit_round12 import decode_log
DATA={p.parent.name:decode_log(p)[0] for p in ROOT.glob('log/round12/game*/ally*')}

def one(game):
 spec=importlib.util.spec_from_file_location('replay_candidate',ROOT/'src/main3.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
 m.print_log=lambda*a,**k:None;m.write_task_trace=lambda*a,**k:None
 sess=m.GameSession(origin=1);sess.trace_turn=lambda*a,**k:None
 times=[];errors=[];task_mismatches=[];actions=0;active=0
 for n,frame in sorted(DATA[game].items()):
  q=frame['request'];start=time.perf_counter()
  try:
   response=sess.handle(copy.deepcopy(q));m.ensure_valid_response(response)
   actions+=len(response['roleCommandMap'])
   if q.get('phaseTask'):
    active+=1
    def task_part(r):
     return dict(prompt=r['prompt'],executeCmd=r['executeCmd'],submits={a:c for a,c in r['roleCommandMap'].items() if c['action']=='submitAnswer'})
    if task_part(response)!=task_part(frame['response']):task_mismatches.append(n)
  except Exception as e:errors.append(dict(round=n,error=repr(e)))
  times.append(1000*(time.perf_counter()-start))
 out=dict(game=game,frames=len(times),actions=actions,active_task_frames=active,task_mismatches=task_mismatches,errors=errors,max_ms=max(times),p95_ms=sorted(times)[int(.95*(len(times)-1))],elapsed_ms=sum(times))
 print('[one]',json.dumps(out,ensure_ascii=False),flush=True);return out
if __name__=='__main__':
 if not DATA:raise SystemExit('[replay_round12] no local Round12 print logs found')
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as ex:out=list(ex.map(one,sorted(DATA)))
 report=dict(scope='Off-policy compatibility replay. Actual subsequent observations are not recomputed. No score or survival inference.',runtime=sys.version,source_sha256=hashlib.sha256((ROOT/'src/main3.py').read_bytes()).hexdigest(),games=out)
 (ROOT/'replay_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
