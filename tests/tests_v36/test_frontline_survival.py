"""Round12 regressions: survival-first shield without stealing funded firepower."""
import copy,json,unittest
from pathlib import Path
from tests_v35.test_capital_clearwave import m,role,data,plan

ROOT=Path(__file__).resolve().parents[1]

class FrontlineSurvivalTests(unittest.TestCase):
 def test_c14_preserves_opening_front_corners_and_flanks(self):
  inputs=json.loads((ROOT/'tests_v36/fixtures/economy_inputs.json').read_text())
  for entry in inputs.values():
   q=copy.deepcopy(entry['initial']);p=plan(q);bx,by=p.base['cell'];sgn=1 if bx<20 else -1
   rel=[(sgn*(2*x-2*bx-1),sgn*(2*y-2*by+1)) for x,y in p.wall_slots]
   self.assertEqual(len(set(rel)),14)
   self.assertEqual(set(rel[:6]),{(5,y) for y in (-5,-3,-1,1,3,5)})
   self.assertEqual(set(rel[6:]),{(x,y) for x in (-3,-1,1,3) for y in (-5,5)})
   self.assertEqual(p.wall_target,10)
 def test_fourteen_target_after_day_one(self):
  self.assertEqual(plan(data(131)).wall_target,14)
 def test_existing_extra_walls_do_not_mask_front_hole(self):
  p=plan(data(391));missing=p.wall_slots[0]
  walls=[role(100+i,'wall',c) for i,c in enumerate(p.wall_slots[1:])]
  walls += [role(200,'wall',(7,20)),role(201,'wall',(7,23))]
  p=plan(data(391,walls=walls));self.assertEqual(p.wall_missing_count(),1)
  self.assertEqual(p.wall_candidate('2'),missing)
 def test_front_hole_preempts_old_side_job(self):
  p=plan(data(391));p.jobs['2']=dict(kind='wall',cell=p.wall_slots[-1]);p.state['front_ever_completed']=True
  self.assertIn(p.wall_candidate('2'),p.wall_slots[:6])
 def test_new_layout_never_requests_demolition(self):
  p=plan(data(391,walls=[role(200,'wall',(7,20)),role(201,'wall',(7,23))]))
  response,_=p.run();self.assertNotIn('remove',[x['action'] for x in response['roleCommandMap'].values()])
 def test_front_floor_schedule_and_flank_cap(self):
  for day in range(1,11):
   p=plan(data(1+(day-1)*130,levels=(3,3,3)));b=p.wall_budget()
   self.assertEqual(b['front_floor_cells'],0 if day<3 else 2 if day==3 else 4 if day==4 else 6)
   self.assertEqual(b['front_floor_level'],1 if day<3 else 2)
   self.assertEqual(b['front_level_cap'],1 if day<3 else 2 if day<6 else 3)
   self.assertEqual(b['flank_level_cap'],1)
 def test_first_two_global_rockets_are_protected(self):
  p=plan(data(521,gold=90,levels=(3,1,1),walls=[role(50,'wall',(12,22),hp=100)]))
  self.assertEqual(p.wall_budget()['front_floor_cells'],0)
  self.assertFalse(p.procure('4'))
 def test_established_core_survives_losing_front_gun_level(self):
  p=plan(data(521,levels=(3,3,2)));q=data(522,levels=(3,1,2))
  p2=plan(q,p.memory);self.assertTrue(p2.wall_budget()['core_battery_established'])
  self.assertEqual(p2.front_floor(dict(cell=p2.wall_slots[0])),2)
 def test_full_front_replacement_is_floor_goal_when_battery_complete(self):
  p=plan(data(521,levels=(3,3,3),walls=[role(50,'wall',(12,22))]))
  self.assertTrue(any(t['id']=='50' and n=='WallUpgradeVoucher1' for _,t,n in p.service_candidates()))
 def test_funded_weapon_precedes_critical_wall(self):
  p=plan(data(521,gold=170,levels=(3,3,2),walls=[role(50,'wall',(12,22),hp=100)]))
  self.assertTrue(p.procure('4'));self.assertEqual(p.v.commands['4']['name'],'WeaponUpgradeVoucher2')
 def test_almost_funded_weapon_not_reset_by_maintenance(self):
  p=plan(data(521,gold=149,levels=(3,3,2),walls=[role(50,'wall',(12,22),hp=100)]))
  self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,149)
 def test_critical_front_can_use_bounded_fallback(self):
  p=plan(data(521,gold=90,levels=(3,3,2),walls=[role(50,'wall',(12,22),hp=100)]))
  self.assertTrue(p.procure('4'));self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher1')
  self.assertEqual(p.v.gold,70);self.assertTrue(any(x.get('event')=='bounded_frontline_fallback' for x in p.events))
 def test_healthy_front_cannot_fallback_while_saving_for_weapon(self):
  p=plan(data(521,gold=90,levels=(3,3,2),walls=[role(50,'wall',(12,22))]))
  self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,90)
 def test_wall_budget_caps_successful_and_reserved_cash(self):
  p=plan(data(521,gold=90,levels=(3,3,2),walls=[role(50,'wall',(12,22),hp=100)]))
  p.state['maintenance_before_battery']=40;self.assertEqual(p.wall_budget()['gold_left'],0)
  self.assertFalse(p.procure('4'))
  p.state['maintenance_before_battery']=20;p.maintenance_reserved=20
  self.assertEqual(p.wall_budget()['gold_left'],0)
 def test_daily_cap_after_battery_complete(self):
  p=plan(data(521,levels=(3,3,3),walls=[role(50,'wall',(12,22),hp=100)]))
  p.state['maintenance_spent']=p.wall_budget()['daily_gold_cap']
  self.assertFalse(any(n.startswith('Wall') for _,_,n in p.service_candidates()))
 def test_other_courier_reservation_protected(self):
  p=plan(data(521,gold=90,levels=(3,3,2),walls=[role(50,'wall',(12,22),hp=100)]))
  p.capital_reserved=80;self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,90)
 def test_destroyed_front_target_not_redirected_to_side_upgrade(self):
  q=data(521,gold=0,levels=(3,3,3),walls=[role(50,'wall',(11,24),hp=100)])
  q['teamOur']['roles'][3].update(pos=dict(x=10,y=24),backpack=['WallUpgradeVoucher1'])
  p=plan(q);p.state['delivery_orders']={'4':[dict(target='999',item='WallUpgradeVoucher1')]}
  self.assertFalse(p.held_delivery('4'));self.assertNotIn('4',p.v.commands)
 def test_carried_capital_does_not_batch_wall(self):
  q=data(521,gold=90,levels=(3,3,2),walls=[role(50,'wall',(12,22),hp=100)])
  q['teamOur']['roles'][3]['backpack']=['WeaponUpgradeVoucher2'];p=plan(q)
  p.state['delivery_orders']={'4':[dict(target='42',item='WeaponUpgradeVoucher2')]}
  self.assertTrue(p.held_delivery('4'));self.assertEqual(p.v.commands['4']['action'],'move')
 def test_healthy_wall_reserves_next_unobserved_weapon_level(self):
  q=data(521,gold=90,levels=(3,3,1),walls=[role(50,'wall',(12,22))])
  q['teamOur']['roles'][1]['backpack']=['WeaponUpgradeVoucher1'];p=plan(q)
  p.state['delivery_orders']={'2':[dict(target='42',item='WeaponUpgradeVoucher1')]}
  self.assertEqual(p.outstanding_weapon_cash(),150)
  self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,90)
 def test_healthy_wall_can_use_true_surplus_after_whole_weapon_chain(self):
  q=data(521,gold=180,levels=(3,3,1),walls=[role(50,'wall',(12,22))])
  q['teamOur']['roles'][1]['backpack']=['WeaponUpgradeVoucher1'];p=plan(q)
  self.assertTrue(p.procure('4'));self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher1')
  self.assertGreaterEqual(p.v.gold,p.outstanding_weapon_cash())
 def test_boundary_purchase_counts_in_total_not_new_day_budget(self):
  p=plan(data(520,levels=(3,3,2)))
  p.memory.previous_actions={'4':dict(action='buy',name='WallUpgradeVoucher1',num=1)}
  # Mimic the committed previous round, then observe the platform purchase feedback.
  p.memory.last_round=520
  q=data(521,levels=(3,3,2));q['lastRoundRoleActionResults']={'4':True}
  p2=plan(q,p.memory)
  self.assertEqual(p2.state['maintenance_before_battery'],20)
  self.assertEqual(p2.state['maintenance_spent'],0)
 def test_missing_enemy_envelope_does_not_record_death(self):
  q=data(521);q['teamEnemy']['roles']=[role(900,'station',(30,10))];p=plan(q)
  q['roundNo']=522;del q['teamEnemy'];p2=plan(q,p.memory)
  self.assertNotIn('first_seen_missing',p2.state['base_observations']['enemy'])
 def test_hidden_next_weapon_voucher_still_protected_when_nearly_funded(self):
  q=data(521,gold=149,levels=(3,3,1),walls=[role(50,'wall',(12,22),hp=100)])
  q['teamOur']['roles'][1]['backpack']=['WeaponUpgradeVoucher1'];p=plan(q)
  self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,149)
 def test_maintenance_phase_cap_resets_only_after_actual_complete_battery(self):
  p=plan(data(521,levels=(3,3,2)));p.state['maintenance_before_battery']=40
  p2=plan(data(522,levels=(3,3,3)),p.memory)
  self.assertEqual(p2.state['maintenance_before_battery'],0)
  p3=plan(data(523,levels=(3,3,1)),p2.memory)
  self.assertGreaterEqual(p3.wall_budget()['gold_left'],20)
 def battle(self,cooldown=0,adjacent=True):
  q=data(611,gold=0,levels=(3,3,3),walls=[role(50,'wall',(12,22),level=2,hp=150)])
  q['robot']['roles']=[dict(role(60,'largeRobot',(13,22),hp=500),targetTeam='challenger')]
  q['teamOur']['roles'][3].update(pos=dict(x=11,y=23) if adjacent else dict(x=10,y=24),backpack=['WallFixer'])
  q['teamOur']['roles'][6]['cooldown']=cooldown
  return plan(q)
 def test_adjacent_repair_cannot_steal_ready_gunner(self):
  p=self.battle(0);self.assertFalse(p.repair_critical_front());self.assertNotIn('4',p.v.busy)
 def test_adjacent_repair_can_use_cooldown(self):
  p=self.battle(2);self.assertTrue(p.repair_critical_front())
  self.assertEqual(p.v.commands['4']['name'],'WallFixer');self.assertEqual(p.v.commands['4']['action'],'use')
 def test_urgent_owned_medicine_precedes_wall_repair(self):
  p=self.battle(2);p.characters['4']['health']=100;p.characters['4']['backpack'].append('Medicine')
  self.assertFalse(p.repair_critical_front());self.assertTrue(p.medicine('4'))
  self.assertEqual(p.v.commands['4']['name'],'Medicine')
 def test_no_travelling_repair_during_live_wave(self):
  p=self.battle(3,False);self.assertFalse(p.repair_critical_front())
 def test_base_observation_not_score_based(self):
  q=data(521);q['teamEnemy']['roles']=[role(900,'station',(30,10))];q['teamOur']['totalScore']=2000
  p=plan(q);q['roundNo']=522;q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=1]
  p2=plan(q,p.memory);obs=p2.state['base_observations']
  self.assertEqual(obs['our']['last_seen_alive'],521);self.assertEqual(obs['our']['first_seen_missing'],522)
  self.assertTrue(obs['enemy']['alive_now']);self.assertNotIn('winner',obs)
 def test_diagnostic_contains_survival_and_floor(self):
  report=plan(data(521,levels=(3,3,3),walls=[role(50,'wall',(12,22))])).run()[1]
  self.assertEqual(report['objective'],'base_survival_before_score')
  self.assertIn('front_readiness',report);self.assertIn('base_observations',report)

if __name__=='__main__':unittest.main()
