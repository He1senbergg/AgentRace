"""Controlled economic trajectory, NOT a battle or score simulator.
Actual starting maps and task packets. Explicit successful sandbox results.
Identical night release times from V3.4 observations, no damage, no robot AI.
Mineral relocation is a fixed-seed free-cell assumption; shop prices stay fixed.
"""
import importlib.util,sys,pickle,json,concurrent.futures,time
from pathlib import Path
from copy import deepcopy
from collections import defaultdict,Counter
from economy_engine import DayEngine,dist,coord,footprint
W=Path(__file__).resolve().parents[1];OUT=W/'runs/v35_economy';OUT.mkdir(parents=True,exist_ok=True);G=json.loads((W/'tests_v35/fixtures/economy_inputs.json').read_text())
def load(name,path):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);m.print_log=lambda*a,**k:None;m.write_task_trace=lambda*a,**k:None;return m

def run_one(name,version,turns=590):
 g=G[name];mod=load('econ_'+version, W/('tests_v35/fixtures/baseline_v34.py' if version=='old' else 'src/main3.py'))
 initial=deepcopy(g['initial']);initial['worldNews']={};initial['teamEnemy']['roles']=[r for r in initial['teamEnemy']['roles'] if r['roleType']=='station']
 points=deepcopy(initial['teamOur']['playerTasks']);templates=g['templates']
 assert sorted(map(len,templates.values()))==[3,3]
 engine=DayEngine(initial,seed=int(name[4:]));session=mod.GameSession(origin=1);session.trace_turn=lambda*a,**k:None
 used=Counter();ready={p['taskType']:1 for p in points};active=None;ended=[];cuts={int((a-1)//130+1):a for a,b in g['idle_nights']};history=[]
 t0=time.monotonic();work=Counter();milestones={};rejected=[]
 for n in range(1,turns+1):
  q=engine.data;day=(n-1)//130+1;rd=(n-1)%130+1
  for pt in q['teamOur']['playerTasks']:
   typ=pt['taskType'];valid=used[typ]<3 and n>=ready[typ];pt.update(isValid=valid,coldDownRounds=max(0,ready[typ]-n),scoreReward=80 if valid else 0,goldReward=80 if valid else 0,timeoutRounds=15 if valid else 0)
  # Threat marker enforces battle time without claiming a private-AI simulation.
  locked=rd>70 and not(day in cuts and n>=cuts[day])
  q['robot']={'roles':[dict(id=2000000000,roleType='smallRobot',pos=dict(x=20,y=0),health=40,targetTeam=q['teamOur']['type'],abnormalState='normal')]} if locked else {'roles':[]}
  for r in q['teamOur']['roles']:
   if r['roleType'] in ('rocket','railgun','gatling'):r['attackRange']={'rocket':(10,15,40),'railgun':(6,8,10),'gatling':(3,5,7)}[r['roleType']][r['level']-1]
  out=session.handle(deepcopy(q));commands=out['roleCommandMap'];feedback={};filtered={};attackers=set();pioneer=next(str(r['id']) for r in q['teamOur']['roles'] if r['roleType']=='pioneer')
  old_cool={str(r['id']):r.get('cooldown',0) for r in q['teamOur']['roles']};task_cash=0;last_result=''
  for actor,c in commands.items():
   action=c['action'];r=next(r for r in q['teamOur']['roles'] if str(r['id'])==actor)
   if action=='attack':
    ctrl=c['controllerId'];assert ctrl not in commands and ctrl not in attackers;assert rd>70 and old_cool[actor]==0
    cr=next(r for r in q['teamOur']['roles'] if str(r['id'])==ctrl);assert dist(coord(cr['pos']),coord(r['pos']))<=1
    attackers.add(ctrl);feedback[actor]=True
   elif action=='acceptTask':
    assert actor==pioneer and active is None
    eligible=[p for p in q['teamOur']['playerTasks'] if p['isValid'] and dist(coord(p['taskPosition']),coord(r['pos']))<=1]
    assert eligible,(name,n,r,q['teamOur']['playerTasks'])
    pt=eligible[0];typ=pt['taskType'];active=dict(typ=typ,template=templates[typ][used[typ]],age=0,start=n+1);feedback[actor]=True
   elif action=='submitAnswer':
    assert actor==pioneer and active is not None
    assert json.loads(c['taskAnswer'])==json.loads(active['template'][3]),(n,c)
    typ=active['typ'];used[typ]+=1;ready[typ]=n+31;task_cash=80;ended.append(n+1);active=None;feedback[actor]=True
   else:filtered[actor]=c
  if out['executeCmd']:
   assert active is not None
   active['age']+=1;assert active['age'] in (1,2)
   last_result=active['template'][active['age']]
  assert not out['prompt'],(name,n,'unexpected_llm')
  # Independent engine validates the economic commands, including night build ban.
  engine.apply(dict(out,roleCommandMap=filtered))
  engine.data['lastRoundRoleActionResults'].update(feedback)
  engine.data['phaseTask']=active['template'][0] if active else ''
  engine.data['lastCmdResult']=last_result
  engine.data['teamOur']['goldNum']+=task_cash
  for r in engine.data['teamOur']['roles']:
   if r['roleType'] in ('rocket','railgun','gatling'):
    ident=str(r['id']);r['cooldown']=3 if commands.get(ident,{}).get('action')=='attack' and r['roleType']=='rocket' else max(0,old_cool.get(ident,0)-1)
  for c in filtered.values():
   if rd>70:work[c['action']]+=1
  if n in [70,130,200,260,330,390,460,520,590]:
   roles=engine.data['teamOur']['roles'];stats=dict(round=n,gold=engine.data['teamOur']['goldNum'],tasks=len(ended),base_level=next(r['level'] for r in roles if r['roleType']=='station'),weapons=sorted((r['level'] for r in roles if r['roleType']=='rocket'),reverse=True),walls=sum(r['roleType']=='wall' for r in roles),mining_gold=engine.stats['mineral_revenue'],maintenance=sum(engine.stats['buy:'+k]*dict((x['name'],x['price']) for x in initial['weaponShopList'])[k] for k in ['WallFixer','WallUpgradeVoucher1','WallUpgradeVoucher2']))
   history.append(stats)
  guns=sorted([r['level'] for r in engine.data['teamOur']['roles'] if r['roleType']=='rocket'],reverse=True)
  for cnt in [1,2,3]:
   if guns.count(3)>=cnt:milestones.setdefault('rocket3_count_'+str(cnt),n+1)
 result=dict(game=name,version=version,elapsed=time.monotonic()-t0,history=history,tasks_end=ended,night_work_commands=dict(work),milestones=milestones,rejected=engine.rejected,stats=dict(engine.stats))
 (OUT/('econ_'+name+'_'+version+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print('[run_one]',name,version,'third_rockets',milestones,'tasks',ended,'end',history[-1],flush=True)
 return result

def pair(name):return [run_one(name,v) for v in ('old','new')]
if __name__=='__main__':
 names=sys.argv[1:] or sorted(G)
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as ex:results=[r for pair_results in ex.map(pair,names) for r in pair_results]
 (OUT/'economy_comparison.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
