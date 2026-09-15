"""Independent economic transitions. No private robot AI or predicted match result."""
from pathlib import Path
import sys,json,copy,pickle,concurrent.futures,time
from collections import Counter
from v37_support import ROOT,load_source
from economy_engine import DayEngine

def one(case):
 game,mode,version=case
 path=ROOT/('tests/tests_v38/fixtures/baseline_v37.py' if version=='V3.7' else 'src/main3.py')
 mod=load_source('economy_'+version,path)
 frames={int(k):v for k,v in json.loads((ROOT/'tests/tests_v38/fixtures/round14_cases.json').read_text())[game].items()}
 n=1 if mode=='opening' else 391
 q=copy.deepcopy(frames[n]['request']);q.update(phaseTask='',llmResp='',lastCmdResult='',errors=[],lastRoundRoleActionResults={})
 q['teamOur']['playerTasks']=[];q['robot']={'roles':[]};q['worldNews']={}
 if mode=='front_cash160':q['teamOur']['goldNum']=160
 if mode=='opening_skew':
  n=1;q=copy.deepcopy(frames[1]['request']);q.update(phaseTask='',llmResp='',lastCmdResult='',errors=[],lastRoundRoleActionResults={});q['teamOur']['playerTasks']=[];q['robot']={'roles':[]};q['worldNews']={}
  base=next(r for r in q['teamOur']['roles'] if r['roleType']=='station');left=base['pos']['x']<20
  q['mapInfo']['zones']=[z for z in q['mapInfo']['zones'] if z['neutralType'] not in ('stone','iron','copper')]
  for kind,xy in [('stone',(38,27)),('copper',(37,28)),('iron',(38,29))]:
   x,y=xy if left else (40-xy[0],31-xy[1]);q['mapInfo']['zones'].append(dict(neutralType=kind,pos=dict(x=x,y=y)))
 engine=DayEngine(q,seed=int(game[4:]),respawn=True);session=mod.GameSession(origin=1);trace=[]
 t0=time.perf_counter()
 for _ in range(70):
  out=session.handle(copy.deepcopy(engine.data));engine.apply(out)
  for a,c in out['roleCommandMap'].items():
   if c['action'] in ('buy','use','build','sell'):trace.append([engine.data['roundNo']-1,a,c])
 w=mod.World(engine.data);mem=mod.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1);delta=mem.observe(w,engine.data['roundNo']);p=mod.SurvivalPlanner(w,mem,delta,mod.Rules())
 row=dict(game=game,mode=mode,version=version,elapsed=time.perf_counter()-t0,
     final_round=engine.data['roundNo'],controllers_at_night=len(p.matching()),gold=engine.data['teamOur']['goldNum'],walls=len(p.walls),
     front_levels=[mod.level_of(r) for r in p.walls if r['cell'] in p.wall_slots[:6]],
     weapons=[dict(cell=r['cell'],level=mod.level_of(r)) for r in p.weapons],stats=dict(engine.stats),rejected=engine.rejected,trace=trace)
 print('[one]',game,mode,version,'walls',row['walls'],'front',row['front_levels'],'guns',len(row['weapons']),'reject',len(row['rejected']),flush=True)
 return row

if __name__=='__main__':
 tasks=[(g,mode,v) for g in ('game91','game92','game94','game100') for mode in ('opening','front_actual','front_cash160','opening_skew') for v in ('V3.7','V3.8')]
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as ex:rows=list(ex.map(one,tasks))
 (ROOT/'runs/v38/economy_probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
