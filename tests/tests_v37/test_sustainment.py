"""Round13 regression contracts. Synthetic geometry is NOT an official battle."""
import unittest, copy
from tests_v35.test_capital_clearwave import m, role, data, plan

def battle(hp=500,cooldown=3,where=(10,22),kits=('WallFixer',)):
 q=data(611,gold=0,levels=(3,3,3),walls=[role(50,'wall',(12,22),2,hp)])
 q['teamOur']['roles'][3].update(pos=dict(x=where[0],y=where[1]),backpack=list(kits))
 q['robot']['roles']=[dict(role(60,'bossRobot',(13,22),hp=800),targetTeam='challenger')]
 for r in q['teamOur']['roles']:
  if r['roleType']=='rocket':r['cooldown']=cooldown
 return q

class MedicineTests(unittest.TestCase):
 def test_full_worker_never_heals_under_any_pressure(self):
  for count in (1,5,12):
   q=battle(kits=('Medicine',));q['teamOur']['roles'][1].update(pos=dict(x=11,y=21),backpack=['Medicine'])
   q['robot']['roles']=[dict(role(100+i,'bossRobot',(13+i%2,21+i//2),hp=800),targetTeam='challenger') for i in range(count)]
   p=plan(q);p.actor_hits['2']=200
   self.assertFalse(p.medicine('2'));self.assertNotIn('2',p.v.commands)
 def test_full_pioneer_never_heals(self):
  p=plan(battle(where=(11,23),kits=('Medicine',)));p.actor_hits['4']=160
  self.assertFalse(p.medicine('4'))
 def test_actual_injury_heals(self):
  q=battle(kits=('Medicine',));q['teamOur']['roles'][3]['health']=70;p=plan(q)
  self.assertTrue(p.medicine('4'));self.assertEqual(p.v.commands['4']['name'],'Medicine')
 def test_slight_injury_without_incoming_damage_does_not_waste_drug(self):
  q=battle(kits=('Medicine',));q['teamOur']['roles'][3]['health']=199;p=plan(q)
  self.assertFalse(p.medicine('4'))
 def test_observed_damage_allows_early_emergency_heal(self):
  q=battle(kits=('Medicine',));q['teamOur']['roles'][3]['health']=140;p=plan(q);p.actor_hits['4']=80
  self.assertTrue(p.medicine('4'))
 def test_no_inventory_no_heal(self):
  q=battle(kits=());q['teamOur']['roles'][3]['health']=50
  self.assertFalse(plan(q).medicine('4'))
 def test_real_damage_only_across_consecutive_observations(self):
  q=battle();p=plan(q);q['roundNo']+=1;q['teamOur']['roles'][3]['health']=160
  p2=plan(q,p.memory);self.assertEqual(p2.actor_hits['4'],40)
  q['roundNo']+=2;q['teamOur']['roles'][3]['health']=120;p3=plan(q,p2.memory)
  self.assertEqual(p3.actor_hits['4'],0)
 def test_personal_inventory_cannot_be_borrowed(self):
  q=battle(kits=('Medicine',));q['teamOur']['roles'][1]['health']=50;p=plan(q)
  self.assertFalse(p.medicine('2'))
 def test_personal_stock_no_more_than_two(self):
  q=data(521,gold=500,levels=(3,3,3));p=plan(q)
  self.assertTrue(p.medicine('4'));self.assertLessEqual(p.v.commands['4']['num'],2)
 def test_shared_funds_not_spent_by_medicine(self):
  p=plan(data(521,gold=10,levels=(3,3,3)));p.capital_reserved=10
  self.assertFalse(p.medicine('4'));self.assertEqual(p.v.gold,10)
 def test_active_night_does_not_buy(self):
  q=battle(kits=());q['teamOur']['goldNum']=100;p=plan(q)
  self.assertFalse(p.medicine('4',True))

class FundingTests(unittest.TestCase):
 def critical(self,gold=90):
  return plan(data(521,gold=gold,levels=(3,3,2),walls=[role(50,'wall',(12,22),hp=100)]))
 def test_no_lifetime_40_gold_starvation(self):
  p=self.critical();p.state['maintenance_before_battery']=400
  self.assertEqual(p.wall_budget()['gold_left'],60);self.assertTrue(p.procure('4'))
 def test_daily_spend_and_reservations_still_bounded(self):
  p=self.critical();p.state['maintenance_spent']=30;p.maintenance_reserved=20
  self.assertEqual(p.wall_budget()['gold_left'],10)
  self.assertFalse(any(n=='WallUpgradeVoucher1' for _,_,n in p.service_candidates()))
 def test_daily_budget_resets_after_spent_yesterday(self):
  p=plan(data(520,levels=(3,3,2)));p.state['maintenance_spent']=60;p.state['maintenance_before_battery']=400
  p2=plan(data(521,levels=(3,3,2)),p.memory);self.assertEqual(p2.wall_budget()['gold_left'],60)
 def test_failed_purchase_not_charged(self):
  p=self.critical();p.memory.previous_actions={'4':dict(action='buy',name='WallFixer',num=2)}
  q=data(522,levels=(3,3,2));q['lastRoundRoleActionResults']={'4':False};p2=plan(q,p.memory)
  self.assertEqual(p2.state['maintenance_spent'],0)
 def test_nearly_funded_third_gun_does_not_forbid_saving_front(self):
  p=self.critical(149);self.assertTrue(p.procure('4'));self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher1')
 def test_critical_front_can_precede_funded_third_gun(self):
  p=self.critical(170);self.assertTrue(p.procure('4'));self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher1')
 def test_funded_second_gun_keeps_priority(self):
  p=plan(data(521,gold=150,levels=(3,2,1),walls=[role(50,'wall',(12,22),hp=100)]))
  self.assertTrue(p.procure('4'));self.assertEqual(p.v.commands['4']['name'],'WeaponUpgradeVoucher2')
 def test_unfunded_emergency_base_allows_affordable_alternative(self):
  p=self.critical(90);p.base['health']=400
  self.assertFalse(p.procure('4',emergency_only=True))
  self.assertTrue(p.procure('4'));self.assertTrue(p.v.commands['4']['name'].startswith('Wall'))
 def test_funded_emergency_base_still_first(self):
  p=self.critical(170);p.base['health']=400
  self.assertTrue(p.procure('4',True));self.assertEqual(p.v.commands['4']['name'],'StationUpgradeVoucher2')
 def test_healthy_front_does_not_drain_gun_savings(self):
  p=self.critical(90);p.walls[0]['health']=1000
  self.assertFalse(p.procure('4'))
 def test_no_negative_cash_with_reservations(self):
  p=self.critical(90);p.capital_reserved=85
  self.assertFalse(p.procure('4'));self.assertFalse(p.stock_repair_kits('4'));self.assertEqual(p.v.gold,90)
 def test_stock_ceiling_three_counts_pending_purchases(self):
  p=self.critical(500);p.characters['2']['backpack']=['WallFixer']
  self.assertTrue(p.stock_repair_kits('4'));self.assertEqual(p.v.commands['4']['num'],2)
  self.assertFalse(any(n=='WallFixer' for _,_,n in p.service_candidates()))
 def test_no_buying_kits_in_full_backpack(self):
  p=self.critical();p.characters['4']['backpack']=['copper']*40
  self.assertFalse(p.stock_repair_kits('4'))
 def test_stock_purchase_uses_real_holder_not_teleport(self):
  p=self.critical();self.assertTrue(p.stock_repair_kits('4'));self.assertIn('4',p.v.commands)
  self.assertNotIn('2',p.v.commands);self.assertEqual(p.v.commands['4']['action'],'buy')
 def test_keep_healthy_base_level_two_voucher(self):
  q=data(521,gold=0,levels=(3,3,3));q['teamOur']['roles'][3].update(pos=dict(x=8,y=23),backpack=['StationUpgradeVoucher2'])
  p=plan(q);self.assertFalse(p.held_delivery('4'))
 def test_damaged_base_uses_preowned_voucher(self):
  q=data(521,gold=0,levels=(3,3,3));q['teamOur']['roles'][0]['health']=1500
  q['teamOur']['roles'][3].update(pos=dict(x=8,y=23),backpack=['StationUpgradeVoucher2']);p=plan(q)
  self.assertTrue(p.held_delivery('4'));self.assertEqual(p.v.commands['4']['action'],'use')
 def test_c14_and_guns_not_repositioned(self):
  p=self.critical();self.assertEqual(len(p.wall_slots),14);self.assertEqual(p.weapon_slots[:3],((8,22),(8,21),(11,22)))

class RepairTests(unittest.TestCase):
 def test_adjacent_cooldown_repair(self):
  p=plan(battle(where=(11,23)));self.assertTrue(p.repair_critical_front());self.assertEqual(p.v.commands['4']['action'],'use')
 def test_one_step_then_repair_is_admissible(self):
  p=plan(battle());self.assertTrue(p.repair_critical_front());self.assertEqual(p.v.commands['4']['action'],'move')
 def test_noncritical_ready_gun_must_fire(self):
  p=plan(battle(hp=800,cooldown=0,where=(11,23)));self.assertFalse(p.repair_critical_front())
 def test_critical_wall_may_cost_one_volley(self):
  p=plan(battle(hp=100,cooldown=0,where=(11,23)));self.assertTrue(p.repair_critical_front())
  self.assertLessEqual(p.events[-1]['projected_missed_volleys'],1)
 def test_cannot_cost_two_volleys(self):
  q=battle(hp=100,cooldown=0,where=(11,23));q['teamOur']['roles'][-1]['pos']=dict(x=12,y=19)
  p=plan(q);route=p.route('4',{(12,19)})
  self.assertGreaterEqual(p.repair_missed_volleys('4',route),2);self.assertFalse(p.repair_critical_front())
 def test_no_repair_without_owned_item(self):
  p=plan(battle(kits=()));self.assertFalse(p.repair_critical_front())
 def test_medicine_before_repair(self):
  q=battle(kits=('Medicine','WallFixer'));q['teamOur']['roles'][3]['health']=100;p=plan(q)
  self.assertFalse(p.repair_critical_front());self.assertTrue(p.medicine('4'))
 def test_upgrade_instead_of_fix_same_wall(self):
  p=plan(battle(where=(11,23),kits=('WallFixer','WallUpgradeVoucher2')))
  self.assertTrue(p.repair_critical_front());self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher2')
 def test_dying_carrier_does_not_charge_front(self):
  q=battle();q['teamOur']['roles'][3]['health']=50;self.assertFalse(plan(q).repair_critical_front())
 def test_expired_target_cancelled(self):
  p=plan(battle());p.state['repair_jobs']={'4':dict(wall='999',until=615,spent_volley=0)}
  p.walls=[];self.assertFalse(p.repair_critical_front());self.assertEqual(p.state['repair_jobs'],{})
 def test_wall_will_die_before_arrival_is_not_chased(self):
  p=plan(battle(hp=5));p.state['wall_rates']={(12,22):40};self.assertFalse(p.repair_critical_front())
 def test_blocked_route_is_not_treated_as_arrival(self):
  p=plan(battle());p.world.occupied.update(m.neighbors(p.characters['4']['cell']));p._paths.clear();p._route_trees.clear()
  self.assertFalse(p.repair_critical_front())
 def test_two_step_outside_gun_coverage_has_bounded_loss(self):
  p=plan(battle(hp=600,where=(9,24),cooldown=3));route=p.route('4',{(12,22)})
  self.assertLessEqual(len(route),4);self.assertGreaterEqual(p.repair_missed_volleys('4',route),0)
 def test_new_wall_id_retains_breach_priority(self):
  q=data(391,levels=(3,3,2),walls=[role(50,'wall',(12,19)),role(51,'wall',(12,22))]);p=plan(q)
  q['roundNo']=392;q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=50];p2=plan(q,p.memory)
  q['roundNo']=393;q['teamOur']['roles'].append(role(55,'wall',(12,19)));p3=plan(q,p2.memory)
  self.assertEqual(p3.priority_fronts()[0]['id'],'55');self.assertEqual(p3.front_floor(p3.priority_fronts()[0]),2)
 def test_healing_not_recorded_as_negative_damage(self):
  q=battle(hp=200);p=plan(q);q['roundNo']+=1;q['teamOur']['roles'][-1]['health']=1500
  p2=plan(q,p.memory);self.assertGreaterEqual(p2.state['wall_rates'][(12,22)],0)
 def test_damage_rate_reset_on_gap(self):
  p=plan(battle());p.state['wall_rates']={(12,22):100};q=battle();q['roundNo']+=3;p2=plan(q,p.memory)
  self.assertNotIn((12,22),p2.state['wall_rates'])

class EscapeRecoveryTests(unittest.TestCase):
 def test_escape_can_leave_all_turrets(self):
  q=battle(where=(11,21),kits=());q['teamOur']['roles'][3]['health']=120;p=plan(q);p.actor_hits['4']=40
  self.assertTrue(p.evade_controller('4'));target=m.position(p.v.commands['4']['targetPos'][0])
  self.assertLessEqual(p.defense.exposure(target),p.defense.exposure((11,21)))
  self.assertLess(p.defense.exposure(p.state['retreats']['4']['target']),p.defense.exposure((11,21)))
 def test_sticky_retreat_not_pulled_back(self):
  q=battle(where=(11,21),kits=());q['teamOur']['roles'][3]['health']=120;p=plan(q);p.actor_hits['4']=40
  self.assertTrue(p.evade_controller('4'));q['roundNo']+=1;q['teamOur']['roles'][3]['pos']=p.v.commands['4']['targetPos'][0]
  p2=plan(q,p.memory);self.assertNotIn('4',p2.return_slots);p2.return_home('4');self.assertNotIn('4',p2.v.commands)
 def test_retreat_cleared_when_wave_cleared(self):
  p=plan(battle());p.state['retreats']={'4':dict(until=615,target=(9,24))}
  q=battle();q['roundNo']+=1;q['robot']['roles']=[];p2=plan(q,p.memory);self.assertEqual(p2.state['retreats'],{})
 def test_full_health_does_not_panic_on_pressure_alone(self):
  p=plan(battle(where=(11,21),kits=()));self.assertFalse(p.evade_controller('4'))
 def test_rebuild_uses_25_not_275_cash(self):
  q=data(521,gold=25,levels=(3,3,2));q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
  q['teamOur']['roles'][1]['pos']=dict(x=11,y=21);p=plan(q);p.state['peak_weapons']=3
  self.assertTrue(p.recover_battery());self.assertTrue(any(c['action']=='build' and c['name']=='rocket' for c in p.v.commands.values()))
 def test_early_four_copper_sale_with_missing_turret(self):
  q=data(521,gold=13,levels=(3,3,2));q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
  q['teamOur']['roles'][2].update(pos=dict(x=19,y=15),backpack=['copper']*4)
  q['teamOur']['roles'][1]['pos']=dict(x=11,y=21);p=plan(q);p.state['peak_weapons']=3
  self.assertTrue(p.recover_battery());self.assertEqual(p.v.commands['3']['action'],'sell')
  self.assertEqual(p.v.commands['3']['num'],4);self.assertIn('2',p.v.busy);self.assertNotIn('2',p.v.commands)
 def test_sell_does_not_spend_same_turn_proceeds(self):
  q=data(521,gold=13,levels=(3,3,2));q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
  q['teamOur']['roles'][2].update(pos=dict(x=19,y=15),backpack=['copper']*4);p=plan(q);p.state['peak_weapons']=3
  p.recover_battery();self.assertEqual(p.v.gold,13);self.assertFalse(any(c['action']=='build' for c in p.v.commands.values()))
 def test_no_rebuild_at_night(self):
  q=battle();q['teamOur']['goldNum']=100;q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
  p=plan(q);p.state['peak_weapons']=3;self.assertFalse(p.recover_battery())
 def test_insufficient_backpack_value_does_not_pretend_financed(self):
  q=data(521,gold=1);q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
  q['teamOur']['roles'][2]['backpack']=['copper'];p=plan(q);p.state['peak_weapons']=3
  self.assertFalse(p.recover_battery())
 def test_rebuild_priority_does_not_liquidate_reserved_stone(self):
  q=data(521,gold=13);q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
  q['teamOur']['roles'][2]['backpack']=['stone']*8;p=plan(q);p.state['peak_weapons']=3;p.wall_reservations['3']=8
  self.assertFalse(p.recover_battery())
 def test_full_battery_does_not_trigger_recovery(self):
  p=plan(data(521));p.state['peak_weapons']=3;self.assertFalse(p.recover_battery())
 def test_diagnostics_include_actual_holder_and_recovery(self):
  r=plan(data(521)).report();self.assertIn('sustainment',r)
  self.assertIn('inventory',r['sustainment']);self.assertIn('actor_hits',r['sustainment'])

if __name__=='__main__':unittest.main()
