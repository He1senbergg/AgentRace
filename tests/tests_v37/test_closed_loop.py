"""Apply NEW actions to a small independent model. Not a private robot simulator.

DayEngine independently checks economy/inventory/movement. Scripted wall pressure
below is a fixed test load, not the official robot AI, pathfinding or scoring.
"""
import unittest,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from v37_support import load_source,memory_from_fixture
from economy_engine import DayEngine,coord,dist
from tests_v37.test_sustainment import battle,data,role
from tests_v37.test_real_cases import case
m=load_source('closed_loop_v37',ROOT/'src/main3.py')
old=load_source('closed_loop_v36',ROOT/'tests/tests_v37/fixtures/baseline_v36.py')
RESULTS=[]

class ScriptedBattle:
 def __init__(self,q):
  self.engine=DayEngine(q,respawn=False);self.fire=0;self.net_repairs=0
 def step(self,out):
  before=copy.deepcopy(self.engine.data);rs={str(r['id']):r for r in before['teamOur']['roles']};shots={};busy=set()
  robots=copy.deepcopy(before['robot']['roles']);old_wall=next(r['health'] for r in before['teamOur']['roles'] if r['id']==50) if any(r['id']==50 for r in before['teamOur']['roles']) else 0
  filtered={}
  for a,c in out['roleCommandMap'].items():
   if c['action']=='attack':
    w=rs[a];ctrl=c['controllerId'];assert ctrl not in busy and ctrl not in out['roleCommandMap']
    assert dist(coord(w['pos']),coord(rs[ctrl]['pos']))<=1 and w['cooldown']==0
    assert w['roleType']=='rocket' and len(c['targetPos'])==w['level']
    busy.add(ctrl);shots[a]=True;self.fire+=1
    for t in c['targetPos']:
     assert 0<dist(coord(w['pos']),coord(t))<=(10,15,40)[w['level']-1]
     for r in robots:
      d=dist(coord(r['pos']),coord(t));r['health']-=20 if d==0 else 10 if d==1 else 0
   else:
    if c['action']=='move':assert coord(c['targetPos'][0]) not in {coord(r['pos']) for r in before['robot']['roles']}
    filtered[a]=c
  self.engine.apply(dict(out,roleCommandMap=filtered));after=self.engine.data
  after['robot']['roles']=[r for r in robots if r['health']>0]
  after['lastRoundRoleActionResults'].update(shots)
  for r in after['teamOur']['roles']:
   if r['roleType']=='rocket':r['cooldown']=3 if str(r['id']) in shots else max(0,rs[str(r['id'])]['cooldown']-1)
  wall=next((r for r in after['teamOur']['roles'] if r['id']==50),None)
  if wall:self.net_repairs+=max(0,wall['health']-old_wall)
  # Explicit synthetic stress: 80HP/round against wall, then front turret.
  if after['robot']['roles']:
   target=wall or next((r for r in after['teamOur']['roles'] if r['id']==42),None)
   if target:target['health']-=80
  after['teamOur']['roles']=[r for r in after['teamOur']['roles'] if r['health']>0]

def run_recovery(mod):
 entry=case('game89',521);engine=DayEngine(entry['request'],seed=89)
 s=mod.GameSession(origin=1);s.memory=memory_from_fixture(entry,mod)
 sales=[];built=[];medicine=[]
 for _ in range(50):
  q=engine.data;out=s.handle(copy.deepcopy(q));n=q['roundNo'];engine.apply(out)
  for a,c in out['roleCommandMap'].items():
   if c['action']=='sell':sales.append([n,a,c['name'],c['num']])
   if c['action']=='build' and c.get('name')=='rocket':built.append(n)
   if c['action']=='use' and c.get('name')=='Medicine':medicine.append(n)
 return dict(build_rounds=built,sales=sales,remaining_gold=engine.data['teamOur']['goldNum'],rejected=engine.rejected,
             scope='Start at actual game89 round521; apply own actions for50 rounds. No robot damage, no new task rewards; mineral relocation is seeded synthetic.' )

class ClosedLoopTests(unittest.TestCase):
 def test_repair_move_then_real_use_and_inventory_decrement(self):
  q=battle(hp=500,cooldown=3);engine=ScriptedBattle(q);s=m.GameSession(origin=1);steps=[]
  for _ in range(3):
   out=s.handle(copy.deepcopy(engine.engine.data));steps.append(copy.deepcopy(out['roleCommandMap'].get('4',{})));engine.step(out)
  self.assertEqual(steps[0]['action'],'move');self.assertEqual((steps[1]['action'],steps[1]['name']),('use','WallFixer'))
  r=next(r for r in engine.engine.data['teamOur']['roles'] if str(r['id'])=='4')
  self.assertNotIn('WallFixer',r['backpack']);self.assertGreater(engine.net_repairs,900)
  RESULTS.append(dict(case='move_use_inventory',steps=steps,net_repair=engine.net_repairs))
 def test_same_scripted_pressure_comparison_records_actual_applied_results(self):
  rows=[]
  for mod,label in ((old,'V3.6'),(m,'V3.7')):
   q=battle(hp=500,cooldown=3);engine=ScriptedBattle(q);s=mod.GameSession(origin=1)
   for _ in range(12):engine.step(s.handle(copy.deepcopy(engine.engine.data)))
   wall=next((r for r in engine.engine.data['teamOur']['roles'] if r['id']==50),None)
   rows.append(dict(version=label,wall_hp=wall['health'] if wall else 0,repair_net=engine.net_repairs,volleys=engine.fire))
  self.assertGreater(rows[1]['repair_net'],rows[0]['repair_net']);self.assertGreater(rows[1]['wall_hp'],rows[0]['wall_hp'])
  RESULTS.append(dict(case='12_turn_scripted_80_damage',results=rows,scope='Fixed synthetic target selection; not official night outcome.'))
 def test_game89_early_sale_closes_rebuild_chain(self):
  a=run_recovery(old);b=run_recovery(m)
  self.assertTrue(b['build_rounds']);self.assertLess(b['build_rounds'][0],551)
  self.assertTrue(b['sales']);self.assertLess(b['sales'][0][0],540)
  self.assertFalse(b['rejected'])
  RESULTS.append(dict(case='game89_recovery',old=a,new=b))
 def test_purchase_then_travel_then_apply_base_insurance(self):
  q=data(521,gold=150,levels=(3,3,3));q['teamOur']['roles'][3]['backpack']=['Medicine']
  engine=DayEngine(q,respawn=False);memory=m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1)
  commands=[]
  for age in range(28):
   q=engine.data
   if age==24:q['teamOur']['roles'][0]['health']=1500 # explicit independent injury injection
   world=m.World(q);delta=memory.observe(world,q['roundNo']);p=m.SurvivalPlanner(world,memory,delta,m.Rules());p.assign_return_slots()
   if age==0:self.assertTrue(p.procure('4'))
   elif not p.held_delivery('4'):p.return_home('4')
   out=m.empty_response();out['roleCommandMap']=p.v.commands;memory.previous_actions=copy.deepcopy(p.v.commands);engine.apply(out)
   commands.append(copy.deepcopy(p.v.commands.get('4',{})))
   if age<24:self.assertEqual(engine.data['teamOur']['roles'][0]['level'],2)
  self.assertEqual(engine.data['teamOur']['roles'][0]['level'],3)
  self.assertEqual(engine.data['teamOur']['roles'][0]['health'],4500)
  self.assertEqual(commands[0].get('name'),'StationUpgradeVoucher2')
  RESULTS.append(dict(case='base_insurance',commands=commands,injury_injected_at_age=24))
 def test_correct_medicine_consumption_follows_applied_injury(self):
  q=battle(kits=('Medicine','Medicine'));engine=DayEngine(q,respawn=False)
  memory=m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1)
  history=[]
  for age in range(6):
   q=engine.data;c=next(r for r in q['teamOur']['roles'] if str(r['id'])=='4')
   if age in (1,4):c['health']=80 # two explicit injury events
   p=m.SurvivalPlanner(m.World(q),memory,memory.observe(m.World(q),q['roundNo']),m.Rules());p.medicine('4')
   response=m.empty_response();response['roleCommandMap']=p.v.commands;memory.previous_actions=copy.deepcopy(p.v.commands);engine.apply(response)
   history.append(dict(age=age,command=p.v.commands,bag=c['backpack'][:]))
  uses=[r for r in history if r['command']];self.assertEqual([r['age'] for r in uses],[1,4])
  self.assertEqual(engine.data['teamOur']['roles'][3]['backpack'],[])
  RESULTS.append(dict(case='medicine_applied_injuries',history=history))

 def test_repairs_abort_after_wall_destruction_between_move_and_use(self):
  q=battle(hp=500,cooldown=3);engine=ScriptedBattle(q);s=m.GameSession(origin=1)
  first=s.handle(copy.deepcopy(engine.engine.data));engine.step(first)
  engine.engine.data['teamOur']['roles']=[r for r in engine.engine.data['teamOur']['roles'] if r['id']!=50]
  out=s.handle(copy.deepcopy(engine.engine.data))
  self.assertFalse(any(c['action']=='use' and c.get('name')=='WallFixer' for c in out['roleCommandMap'].values()))
  self.assertEqual(s.memory.survival['repair_jobs'],{})

 def test_dead_carrier_does_not_leave_stale_job(self):
  q=battle();engine=ScriptedBattle(q);s=m.GameSession(origin=1);engine.step(s.handle(copy.deepcopy(engine.engine.data)))
  engine.engine.data['teamOur']['roles']=[r for r in engine.engine.data['teamOur']['roles'] if r['id']!=4]
  out=s.handle(copy.deepcopy(engine.engine.data));self.assertNotIn('4',out['roleCommandMap']);self.assertNotIn('4',s.memory.survival['repair_jobs'])

 @classmethod
 def tearDownClass(cls):
  out=ROOT/'runs/v37';out.mkdir(parents=True,exist_ok=True)
  (out/'closed_loop_validation.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2))

if __name__=='__main__':unittest.main()
