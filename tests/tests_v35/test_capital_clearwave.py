"""Behavior regressions for Round11, not assertions of official match scores."""
import sys,importlib.util,unittest,copy,json
from pathlib import Path
W=Path(__file__).resolve().parents[2]
sp=importlib.util.spec_from_file_location('v35_tests_module',W/'src/main3.py')
m=importlib.util.module_from_spec(sp);sys.modules[sp.name]=m;sp.loader.exec_module(m)
m.print_log=lambda *a,**k:None;m.GameSession.trace_turn=lambda *a,**k:None
initial=json.loads((W/'tests/tests_v34/fixtures/states.json').read_text())['game43']['0']['request']
def role(i,kind,cell,level=1,hp=None,bag=()):
 return dict(id=i,roleType=kind,pos=dict(zip(('x','y'),cell)),level=level,
  health=(220 if kind=='worker' else 200 if kind=='pioneer' else 1500*level if kind=='station' else 500+500*level) if hp is None else hp,
  backpack=list(bag),backPackCapability=100 if kind=='worker' else 40 if kind=='pioneer' else 0,cooldown=0)
def data(n=261,gold=200,levels=(3,1,1),walls=()):
 q=copy.deepcopy(initial);q.update(roundNo=n,phaseTask='',llmResp='',lastCmdResult='',lastRoundRoleActionResults={},errors=[],robot={'roles':[]})
 q['teamOur'].update(type='challenger',goldNum=gold,playerTasks=[],roles=[role(1,'station',(9,22),2),role(2,'worker',(7,22)),role(3,'worker',(7,21)),role(4,'pioneer',(24,19)),role(40,'rocket',(8,22),levels[0]),role(41,'rocket',(8,21),levels[1]),role(42,'rocket',(11,22),levels[2]),*walls])
 q['teamEnemy']['roles']=[];return q
def plan(q,memory=None):
 memory=memory or m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1)
 w=m.World(q);d=memory.observe(w,q['roundNo']);p=m.SurvivalPlanner(w,memory,d,m.Rules());p.assign_return_slots();return p
class CapitalClearwaveTests(unittest.TestCase):
 def test_clear_night_releases_without_making_it_day(self):
  p=plan(data(101));self.assertTrue(p.night_cleared);self.assertFalse(p.phase.is_day);self.assertEqual(p.work_turns,100)
  response,report=p.run();self.assertEqual(report['mode'],'NIGHT_WORK');self.assertTrue(response['roleCommandMap']);self.assertNotIn('build',[c['action'] for c in response['roleCommandMap'].values()])
 def test_spawn_round_not_clear_even_with_empty_array(self):
  p=plan(data(71));self.assertFalse(p.night_cleared);self.assertEqual(p.work_turns,0)
 def test_own_robot_anywhere_keeps_defense(self):
  q=data(101);q['robot']['roles']=[dict(role(60,'smallRobot',(40,31),hp=40),targetTeam='challenger')]
  self.assertFalse(plan(q).night_cleared)
 def test_unknown_robot_target_keeps_defense(self):
  q=data(101);q['robot']['roles']=[role(60,'smallRobot',(40,31),hp=40)]
  self.assertFalse(plan(q).night_cleared)
 def test_malformed_robot_does_not_imply_empty_field(self):
  for v in (None,{}, {'roles':None},{'roles':[None]},{'roles':[{'id':60}]}):
   q=data(101);q['robot']=v;self.assertFalse(plan(q).night_cleared)
 def test_other_side_robots_block_corridors_not_all_work(self):
  q=data(101);q['robot']['roles']=[dict(role(60,'smallRobot',(20,16),hp=40),targetTeam='defender')]
  p=plan(q);self.assertTrue(p.night_cleared);self.assertIn((20,16),p.work_hazards);self.assertIn((24,20),p.work_hazards)
  path=p.path((10,16),{(30,16)},False);self.assertTrue(path);self.assertFalse(set(path)&set(p.work_hazards))
 def test_foreign_robot_near_base_blocks_release(self):
  q=data(101);q['robot']['roles']=[dict(role(60,'smallRobot',(15,22),hp=40),targetTeam='defender')]
  self.assertFalse(plan(q).night_cleared)
 def test_clearance_revoked_when_enemy_reappears(self):
  p=plan(data(101));q=data(102);q['robot']['roles']=[dict(role(60,'smallRobot',(40,31),hp=40),targetTeam='challenger')]
  p2=plan(q,p.memory);self.assertFalse(p2.night_cleared);self.assertEqual(p2.work_turns,0)
 def test_final_night_budget_does_not_go_beyond_1300(self):
  self.assertEqual(plan(data(1290)).work_turns,11)
 def test_actual_day_boundary_and_zero_origin(self):
  self.assertEqual(plan(data(130)).work_turns,71);self.assertEqual(plan(data(131)).work_turns,70)
  q=data(100);mem=m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=0)
  self.assertEqual(plan(q,mem).work_turns,100)
 def test_night_build_gate_still_rejects(self):
  p=plan(data(101));p.characters['2']['backpack']=['stone']
  self.assertFalse(p.v.add('2',dict(action='build',name='wall',targetPos=[dict(x=7,y=23)])))
 def test_clear_night_courier_can_apply_owned_voucher_after_travel(self):
  q=data(101,gold=0);q['teamOur']['roles'][3]['backpack']=['WeaponUpgradeVoucher1']
  p=plan(q);p.state['delivery_orders']={'4':[dict(target='41',item='WeaponUpgradeVoucher1')]}
  self.assertTrue(p.held_delivery('4'));self.assertEqual(p.v.commands['4']['action'],'move')
 def test_unfinished_tasks_admitted_on_safe_night(self):
  q=data(101);q['teamOur']['roles'][3]['pos']=dict(x=15,y=17)
  q['teamOur']['playerTasks']=[dict(taskType='test',taskPosition=dict(x=16,y=17),isValid=True,coldDownRounds=0,timeoutRounds=10)]
  p=plan(q);self.assertTrue(m.TaskPlanner(p.v).plan_next_task());self.assertEqual(p.v.commands['4']['action'],'acceptTask')
 def test_unfinished_tasks_not_admitted_into_live_wave(self):
  q=data(101);q['teamOur']['roles'][3]['pos']=dict(x=15,y=17);q['teamOur']['playerTasks']=[dict(taskType='test',taskPosition=dict(x=16,y=17),isValid=True,coldDownRounds=0,timeoutRounds=10)]
  q['robot']['roles']=[dict(role(60,'smallRobot',(40,31),hp=40),targetTeam='challenger')]
  self.assertFalse(m.TaskPlanner(plan(q).v).plan_next_task())
 def test_weapon_goal_beats_even_critical_wall_purchase(self):
  p=plan(data(walls=[role(50,'wall',(12,22),hp=100)]));goals=p.service_candidates()
  self.assertEqual(goals[0][1]['roleType'],'rocket');self.assertTrue(all(pri>=60 for pri,t,n in goals if n.startswith('Wall')))
 def test_no_pre_stock_goal_can_hide_unaffordable_gun(self):
  p=plan(data(gold=99,walls=[role(50,'wall',(12,22),hp=1000)]));self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,99)
  self.assertEqual(p.state['capital_goal']['item'],'WeaponUpgradeVoucher1')
 def test_wall_level_caps_depend_on_guns_and_day(self):
  for day in range(1,11):
   p=plan(data(1+(day-1)*130));policy=p.wall_budget();self.assertEqual(policy['front_level_cap'],1)
   p=plan(data(1+(day-1)*130,levels=(3,3,3)));policy=p.wall_budget()
   self.assertEqual(policy['front_level_cap'],1 if day<=2 else 2 if day<=5 else 3)
   self.assertEqual(policy['flank_level_cap'],1 if day<5 else 2)
 def test_two_global_guns_allow_only_front_level_two(self):
  p=plan(data(391,levels=(3,3,1),walls=[role(50,'wall',(12,22),hp=100),role(51,'wall',(12,21),level=2,hp=100)]))
  self.assertTrue(any(t['id']=='50' and n=='WallUpgradeVoucher1' for _,t,n in p.service_candidates()))
  self.assertFalse(any(n=='WallUpgradeVoucher2' for _,t,n in p.service_candidates()))
 def test_wall_daily_cash_cap_respected(self):
  p=plan(data(391,levels=(3,3,3),walls=[role(50,'wall',(12,22),hp=100)]));p.state['maintenance_spent']=40
  self.assertFalse(any(n.startswith('Wall') for _,t,n in p.service_candidates()))
 def test_stock_deficit_count_not_repeated_per_wall(self):
  p=plan(data(651,levels=(3,3,3),walls=[role(50,'wall',(12,22),3,2000),role(51,'wall',(12,21),3,2000)]))
  p.characters['4']['backpack']=['WallFixer'];self.assertEqual(sum(n=='WallFixer' for _,t,n in p.service_candidates()),1)
  p.characters['4']['backpack']=['WallFixer','WallFixer'];self.assertEqual(sum(n=='WallFixer' for _,t,n in p.service_candidates()),0)
 def test_stock_deficit_not_subtracted_twice_in_purchase_coverage(self):
  p=plan(data(651,levels=(3,3,3),walls=[role(50,'wall',(12,22),3,2000),role(51,'wall',(12,21),3,2000)]))
  p.characters['4']['backpack']=['WallFixer']
  self.assertEqual(sum(n=='WallFixer' for _,t,n in p.uncovered_capital()),1)
 def test_no_fix_before_owned_upgrade_for_same_wall(self):
  q=data(391,levels=(3,3,3),walls=[role(50,'wall',(12,22),1,300)]);q['teamOur']['roles'][3].update(pos=dict(x=13,y=22),backpack=['WallFixer','WallUpgradeVoucher1'])
  p=plan(q);p.state['delivery_orders']={'4':[dict(target='50',item='WallFixer'),dict(target='50',item='WallUpgradeVoucher1')]}
  self.assertTrue(p.held_delivery('4'));self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher1')
 def test_shared_inflight_cash_not_spent_on_healthy_medicine(self):
  p=plan(data(gold=100));self.assertTrue(p.procure('2'));self.assertEqual(p.capital_reserved,100)
  self.assertFalse(p.medicine('4'));self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,100)
 def test_different_uncovered_target_after_first_claim(self):
  p=plan(data(gold=300));self.assertTrue(p.procure('2'));first=p.jobs['2']['target']
  self.assertTrue(p.procure('4'));self.assertNotEqual(first,p.jobs['4']['target'])
 def test_held_stock_does_not_double_cover_two_weapons(self):
  q=data();q['teamOur']['roles'][1]['backpack']=['WeaponUpgradeVoucher1']
  p=plan(q);p.state['delivery_orders']={'2':[dict(target='41',item='WeaponUpgradeVoucher1')]}
  rows=p.uncovered_capital();self.assertFalse(any(t['id']=='41' for _,t,n in rows));self.assertTrue(any(t['id']=='42' for _,t,n in rows))
 def test_broken_base_rescue_is_not_suppressed_by_firepower(self):
  q=data();q['teamOur']['roles'][0]['health']=100;p=plan(q);self.assertEqual(p.service_candidates()[0][0],0)
 def test_medicine_not_overstocked_on_healthy_courier(self):
  p=plan(data());self.assertTrue(p.medicine('4'));self.assertEqual(p.v.commands['4']['num'],1)
 def test_print_report_contains_live_economy_and_budget(self):
  report=plan(data(101)).run()[1]
  for key in ('work_turns','night_cleared','wall_budget','capital_reservations'):self.assertIn(key,report)
 def test_batch_purchase_cannot_spend_another_courier_reservation(self):
  q=data(gold=200);q['teamOur']['roles'][3]['backpack']=['WeaponUpgradeVoucher1']
  p=plan(q);p.state['capital_targets']={'4':dict(target='41',item='WeaponUpgradeVoucher1')}
  p.state['delivery_orders']={'4':[dict(target='41',item='WeaponUpgradeVoucher1')]}
  self.assertTrue(p.procure('2'));self.assertEqual(p.capital_reserved,100)
  self.assertTrue(p.held_delivery('4'));self.assertNotEqual(p.v.commands['4']['action'],'buy')
 def test_quarry_resets_yesterdays_single_stone_quota(self):
  p=plan(data(131));p.jobs['2']=dict(kind='wall',stage='build',quota=1,batch_day=1)
  p.world.zones['stone']={(5,22)};p.static.occupied.add((5,22));p.world.occupied.add((5,22))
  self.assertTrue(p.build_walls('2'));self.assertGreater(p.jobs['2']['quota'],1)
 def test_maintenance_previous_night_is_not_charged_to_next_day(self):
  p=plan(data(260));p.state['maintenance_spent']=20
  p.memory.previous_actions={'4':dict(action='buy',name='WallFixer',num=1)}
  q=data(261);q['lastRoundRoleActionResults']={'4':True};p2=plan(q,p.memory)
  self.assertEqual(p2.state['maintenance_spent'],0)
if __name__=='__main__':unittest.main()
