import sys,importlib.util,unittest,pickle,copy,random,json,types
from pathlib import Path
W=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('frontline_release',W/'src/main3.py');m=importlib.util.module_from_spec(sp);sys.modules[sp.name]=m;sp.loader.exec_module(m)
m.print_log=lambda *a,**k:None;m.GameSession.trace_turn=lambda *a,**k:None
rows={g:{int(k):v for k,v in states.items()} for g,states in json.loads((W/'tests_v34/fixtures/states.json').read_text(encoding='utf-8')).items()}
def role(a,k,p,level=1,hp=None,bag=()):
 return dict(id=a,roleType=k,pos=dict(x=p[0],y=p[1]),level=level,health=hp or (220 if k=='worker' else 200 if k=='pioneer' else 1500*level if k=='station' else 500+500*level),backpack=list(bag),backPackCapability=100 if k=='worker' else 40 if k=='pioneer' else 0,cooldown=0)
def data(r=131,extra=None):
 q=copy.deepcopy(rows['game43'][0]['request']);q['roundNo']=r;q['phaseTask']='';q['teamOur']['roles']=[role(1,'station',(9,22),2),role(2,'worker',(7,22)),role(3,'worker',(7,21)),role(4,'pioneer',(11,21)),role(40,'rocket',(8,22),3),role(41,'rocket',(8,21),2),role(42,'rocket',(11,22),1)];q['teamOur']['goldNum']=800;q['teamOur']['playerTasks']=[];q['robot']={'roles':[]};q['teamEnemy']['roles']=[];q['lastRoundRoleActionResults']={};q['errors']=[]
 if extra:q['teamOur']['roles']+=extra
 return q

def planner(q,mem=None):
 mem=mem or m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1)
 w=m.World(q);d=mem.observe(w,q['roundNo']);return m.SurvivalPlanner(w,mem,d,m.Rules())
class FrontlineTests(unittest.TestCase):
 def test_c_layout_all_initial_maps_and_free_service(self):
  for name,x in rows.items():
   q=copy.deepcopy(x[0]['request']);p=planner(q);base=p.base['cell'];cx,cy=2*base[0]+1,2*base[1]-1;sign=1 if cx<40 else -1
   self.assertEqual(len(set(p.wall_slots)),14,name);self.assertTrue(set(p.wall_slots)<=m.building_ring(base,2))
   self.assertTrue(all(sign*(2*z[0]-cx)>-5 for z in p.wall_slots))
   self.assertEqual(len(set(p.weapon_slots[:3])),3);self.assertTrue(set(p.weapon_slots[:3])<=m.building_ring(base,1))
   blocked=set(p.wall_slots)|set(p.weapon_slots[:3])|m.station_cells(base)
   for cell in p.weapon_slots[:3]:
    self.assertGreaterEqual(len(set(m.neighbors(cell))-blocked),2,(name,cell))
 def test_cached_paths_equal_original_bfs_with_dynamic_reservations(self):
  for name,x in rows.items():
   for index in [0,69,199,329]:
    p=planner(copy.deepcopy(x[index]['request']))
    for char in p.characters.values():
     start=char['cell']
     for static in (False,True):
      for target in [*p.wall_slots[:2],*p.weapon_slots[:3],(20,16),(25,20)]:
       for adjacent in (False,True):
        geometry=p.static if static else p.world
        reserved=set() if static else set(p.v.targets)
        goals=geometry.adjacent_goals({target},start) if adjacent else {target}
        self.assertEqual(p.path(start,{target},adjacent,static),geometry.path(start,goals,reserved),(name,index,start,target,static,adjacent))
 def test_cooling_zero_timeout_waits_only_after_success(self):
  q=data(160);q['teamOur']['roles'][3]['pos']={'x':15,'y':17}
  q['teamOur']['playerTasks']=[dict(taskType='test',taskPosition={'x':16,'y':17},coldDownRounds=5,isValid=False,scoreReward=0,goldReward=0,timeoutRounds=0)]
  p=planner(q);self.assertFalse(m.TaskPlanner(p.v).plan_next_task())
  cells=tuple(sorted(p.world.zones['challengerTaskPoint2']));p.memory.fast_task_points[cells]=dict(duration=3,skill='deployment_crlf_v34')
  self.assertTrue(m.TaskPlanner(p.v).plan_next_task());self.assertIn('4',p.v.busy);self.assertEqual(p.v.commands,{})
 def test_exhausted_point_not_waited_or_accepted(self):
  q=data(160);q['teamOur']['roles'][3]['pos']={'x':15,'y':17};q['teamOur']['playerTasks']=[dict(taskPosition={'x':16,'y':17},coldDownRounds=0,isValid=False,timeoutRounds=0)]
  p=planner(q);p.memory.fast_task_points[tuple(sorted(p.world.zones['challengerTaskPoint2']))]=dict(duration=3)
  self.assertFalse(m.TaskPlanner(p.v).plan_next_task())
 def test_cooling_offer_reordered_does_not_change_task_choice(self):
  q=copy.deepcopy(rows['game46'][0]['request']);s=m.GameSession(origin=1);a=s.handle(q)
  q['teamOur']['playerTasks'].reverse();t=m.GameSession(origin=1);self.assertEqual(a,t.handle(q))
 def test_no_success_learning_from_errors_or_discontinuous_or_bad_feedback(self):
  for error,gap,feedback in [([{'errorCode':1}],False,{'4':True}),([{'errorCode':2}],False,{'4':True}),([],True,{'4':True}),([],False,[]),([],False,{'4':False})]:
   q=data(14 if gap else 13);q['errors']=error;q['lastRoundRoleActionResults']=feedback
   mem=m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1);mem.last_round=12
   mem.previous_actions={'4':{'action':'submitAnswer','taskAnswer':'{}'}}
   mem.task=dict(actor='4',pending=('submit',12),skill_used='deployment_crlf_v34',cells=[(16,17)],started_round=10)
   mem.observe(m.World(q),q['roundNo']);self.assertEqual(mem.fast_task_points,{})
 def test_success_learning_requires_ended_after_valid_submit(self):
  q=data(13);q['lastRoundRoleActionResults']={'4':True}
  mem=m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1);mem.last_round=12;mem.previous_actions={'4':{'action':'submitAnswer','taskAnswer':'{}'}}
  mem.task=dict(actor='4',pending=('submit',12),skill_used='deployment_crlf_v34',cells=[(16,17)],started_round=10)
  mem.observe(m.World(q),13);self.assertEqual(mem.fast_task_points[((16,17),)]['duration'],3)
 def test_hot_wall_upgrade_does_not_wait_for_all_guns_level_three(self):
  q=data(261,[role(50,'wall',(12,22),1,400)]);p=planner(q)
  self.assertTrue(any(w['id']=='50' and n=='WallUpgradeVoucher1' and pri<24 for pri,w,n in p.service_candidates()))
 def test_untouched_rear_never_upgraded(self):
  p=planner(data(261,[role(50,'wall',(7,22),1,200)]))
  self.assertFalse(any(t['id']=='50' for _,t,_ in p.service_candidates()))
 def test_maintenance_spending_bound(self):
  p=planner(data(261,[role(50,'wall',(12,22),1,200)]));p.state['maintenance_spent']=120
  self.assertFalse(any(n.startswith('Wall') for _,_,n in p.service_candidates()))
 def test_missile_levels_have_real_aoe_benefit(self):
  q=data(331);q['robot']={'roles':[dict(role(60+i,'smallRobot',xy,hp=200),targetTeam=q['teamOur']['type']) for i,xy in enumerate([(15,22),(15,23),(16,22),(16,23)])]}
  p=planner(q);w=next(w for w in p.weapons if w['id']=='40');w.update(cell=(8,22),level=3,attackRange=40)
  targets,after,score=p.defense.attack_plan(w);damage=sum(p.defense.remaining.values())-sum(after.values())
  self.assertEqual(len(targets),3);self.assertGreater(damage/4,30)
 def test_adjacent_emergency_repair_uses_owned_item(self):
  q=data(341,[role(50,'wall',(12,22),3,150)]);q['teamOur']['roles'][3]['backpack']=['WallFixer'];q['robot']={'roles':[dict(role(60,'largeRobot',(13,22),hp=500),targetTeam=q['teamOur']['type'])]}
  p=planner(q);self.assertTrue(p.repair_critical_front());self.assertEqual(p.v.commands['4']['action'],'use');self.assertEqual(p.v.commands['4']['name'],'WallFixer')
 def test_no_repairs_faked_without_inventory(self):
  q=data(341,[role(50,'wall',(12,22),3,150)]);q['robot']={'roles':[dict(role(60,'largeRobot',(13,22),hp=500),targetTeam=q['teamOur']['type'])]}
  p=planner(q);self.assertFalse(p.repair_critical_front());self.assertEqual(p.v.commands,{})
 def test_manifest_preserves_first_goal_across_batch(self):
  q=data();q['teamOur']['roles'][1]['pos']={'x':11,'y':23};q['teamOur']['roles'][1]['backpack']=['WeaponUpgradeVoucher1','WeaponUpgradeVoucher2']
  q['teamOur']['roles'][4]['level']=2;q['teamOur']['roles'][4]['health']=1500
  p=planner(q);p.state['delivery_orders']={'2':[{'target':'40','item':'WeaponUpgradeVoucher2'},{'target':'42','item':'WeaponUpgradeVoucher1'}]};p.assign_return_slots()
  self.assertTrue(p.held_delivery('2'));self.assertEqual(p.jobs['2']['target'],'40')
 def test_failed_purchase_does_not_create_phantom_owned_item(self):
  q=data();p=planner(q);p.state['delivery_orders']={'2':[{'target':'40','item':'WeaponUpgradeVoucher2'}]}
  p.memory.last_round=131;p.memory.previous_actions={'2':dict(action='buy',name='WeaponUpgradeVoucher2',num=1)};q['roundNo']=132;q['lastRoundRoleActionResults']={'2':False}
  nxt=planner(q,p.memory);self.assertEqual(nxt.state['delivery_orders']['2'],[])
 def test_preemptive_stock_two_fixers_bound(self):
  q=data(261,[role(50,'wall',(12,22),3,2000),role(51,'wall',(12,21),3,2000)]);p=planner(q)
  self.assertTrue(any(n=='WallFixer' for _,_,n in p.service_candidates()))
  q['teamOur']['roles'][3]['backpack']=['WallFixer']*2;p=planner(q)
  self.assertFalse(any(n=='WallFixer' for _,_,n in p.service_candidates()))
 def test_pioneer_prepositions_without_spending_future_gold(self):
  q=data(261);q['teamOur']['goldNum']=50;p=planner(q);p.assign_return_slots()
  self.assertFalse(p.procure('4'));self.assertTrue(p.stage_courier('4'))
  self.assertEqual(p.v.commands['4']['action'],'move');self.assertEqual(p.v.gold,50)
 def test_courier_goes_home_to_its_paid_upgrade_target(self):
  q=data(261);q['teamOur']['roles'][3]['pos']={'x':24,'y':19};q['teamOur']['roles'][3]['backpack']=['WeaponUpgradeVoucher2']
  p=planner(q);p.state['delivery_orders']={'4':[{'target':'41','item':'WeaponUpgradeVoucher2'}]};p.assign_return_slots()
  self.assertLessEqual(m.distance(p.return_slots['4'],p.world.roles['41']['cell']),1)
 def test_second_global_rocket_before_third_half_upgrade(self):
  p=planner(data(261));c=[(priority,t['id'],n) for priority,t,n in p.service_candidates()]
  self.assertLess(next(x[0] for x in c if x[1]=='41'),next(x[0] for x in c if x[1]=='42'))
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(FrontlineTests);r=unittest.TextTestRunner(verbosity=2).run(suite)
 (W/'frontline_validation.json').write_text(json.dumps({'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'successful':r.wasSuccessful()},indent=2));sys.exit(not r.wasSuccessful())
