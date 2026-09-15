"""V3.8 contracts. Geometry and independent transitions, not official match wins."""
import unittest,copy,json,sys
from pathlib import Path
from tests_v35.test_capital_clearwave import m,role,data,plan
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from economy_engine import DayEngine

def scenario(n=391,gold=160,levels=(3,2,2),wall_level=1,count=14,base_level=2):
    q=data(n,gold,levels)
    q['teamOur']['roles'][0].update(level=base_level,health=1500*base_level)
    for idx,xy in zip((4,5,6),((8,23),(8,21),(8,20))):
        q['teamOur']['roles'][idx]['pos']=dict(zip(('x','y'),xy))
    q['teamOur']['roles'][1]['pos']=dict(x=8,y=22)
    q['teamOur']['roles'][2]['pos']=dict(x=9,y=20)
    p=plan(q)
    q['teamOur']['roles'] += [role(50+i,'wall',c,wall_level if i<6 else 1) for i,c in enumerate(p.wall_slots[:count])]
    return q

def staffed(q):
    q['teamOur']['roles'][3]['pos']=dict(x=9,y=23)
    return q

def pressure_q():
    q=staffed(scenario(501,0,(3,3,3),2))
    q['teamEnemy']['roles']=[role(800,'station',(30,10),2),role(801,'wall',(28,10),2,600),role(802,'wall',(28,9),2,900)]
    return q

class RearLayout(unittest.TestCase):
    def test_primary_three_are_rear_and_staggered(self):
        p=plan(scenario());self.assertEqual(p.weapon_slots[:3],((8,23),(8,21),(8,20)))
        self.assertTrue(all(c in m.building_ring(p.base['cell'],1) for c in p.weapon_slots[:3]))
    def test_mirror_uses_own_base_not_team_label(self):
        q=scenario(count=0);q['teamOur']['roles'][0]['pos']=dict(x=30,y=10)
        p=plan(q);self.assertEqual(p.weapon_slots[:3],((32,8),(32,10),(32,11)))
        self.assertEqual(p.gate_cell,(33,9))
    def test_first_fourteen_remain_C_and_front_six(self):
        p=plan(scenario());self.assertEqual(len(p.wall_slots),18);self.assertEqual(p.wall_target,14)
        self.assertEqual(set(p.wall_slots[:6]),{(12,y) for y in range(19,25)})
        self.assertNotIn((7,22),p.wall_slots);self.assertEqual(len(set(p.wall_slots)),18)
    def test_G18_has_three_distinct_operator_slots(self):
        p=plan(staffed(scenario(391,1000,(3,3,3),2,18)))
        self.assertEqual(len(p.return_slots),3);self.assertEqual(len(set(p.return_slots.values())),3)
        self.assertEqual(len(p.matching()),3)
    def test_last_rear_wall_preserves_paths(self):
        q=staffed(scenario(391,1000,(3,3,3),2,17));p=plan(q)
        self.assertTrue(p.construction_safe(p.wall_slots[17]))
    def test_main_gate_sealing_is_rejected(self):
        p=plan(staffed(scenario(391,1000,(3,3,3),2,18)))
        self.assertFalse(p.construction_safe(p.gate_cell))
    def test_existing_front_gun_not_demolished(self):
        q=data(391,200,(3,3,3));p=plan(q);p.build_weapon('2');self.assertEqual(p.v.commands,{})
    def test_25_gold_rebuilds_rear_without_upgrade_reserve(self):
        q=scenario(391,25,count=0);q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
        p=plan(q);p.state['peak_weapons']=3;self.assertTrue(p.recover_battery())
        builds=[c for c in p.v.commands.values() if c['action']=='build']
        self.assertEqual(len(builds),1);self.assertEqual(builds[0]['targetPos'],[dict(x=8,y=20)])
    def test_four_copper_sale_does_not_finance_same_turn_build(self):
        q=scenario(391,13,count=0);q['teamOur']['roles']=[r for r in q['teamOur']['roles'] if r['id']!=42]
        q['teamOur']['roles'][1].update(pos=dict(x=19,y=15),backpack=['copper']*4)
        p=plan(q);p.state['peak_weapons']=3;self.assertTrue(p.recover_battery())
        self.assertEqual(p.v.commands['2']['action'],'sell');self.assertEqual(p.v.commands['2']['num'],4)
        self.assertFalse(any(c['action']=='build' for c in p.v.commands.values()));self.assertEqual(p.v.gold,13)

class FrontProject(unittest.TestCase):
    def test_day3_three_day4_six_floor(self):
        for n,num in ((261,3),(391,6),(521,6)):
            p=plan(scenario(n));self.assertEqual(sum(p.front_floor(w)==2 for w in p.walls),num)
    def test_no_core_no_expensive_floor(self):
        p=plan(scenario(levels=(2,2,1)));self.assertEqual(p.wall_budget()['front_floor_cells'],0)
    def test_day4_140_budget_not_infinite(self):
        p=plan(scenario());self.assertEqual(p.wall_budget()['daily_gold_cap'],140)
        p.state['maintenance_spent']=100;p.maintenance_reserved=30;self.assertEqual(p.wall_budget()['gold_left'],10)
        self.assertFalse(any(n=='WallUpgradeVoucher1' for _,_,n in p.service_candidates()))
    def test_daily_budget_reset_preserves_finite_cap(self):
        p=plan(scenario(390));p.state['maintenance_spent']=140
        p2=plan(scenario(391),p.memory);self.assertEqual(p2.wall_budget()['gold_left'],140)
    def test_healthy_floor_can_precede_second_level3(self):
        p=plan(scenario(gold=160));self.assertTrue(p.procure('4'))
        self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher1')
    def test_first_global_still_precedes_wall_floor(self):
        p=plan(scenario(gold=160,levels=(2,2,2)));self.assertTrue(p.procure('4'))
        self.assertEqual(p.v.commands['4']['name'],'WeaponUpgradeVoucher2')
    def test_second_level2_still_precedes_wall_floor(self):
        p=plan(scenario(gold=160,levels=(3,1,1)));self.assertTrue(p.procure('4'))
        self.assertEqual(p.v.commands['4']['name'],'WeaponUpgradeVoucher1')
    def test_bounded_three_voucher_batch(self):
        p=plan(scenario(gold=160));self.assertTrue(p.procure('4'))
        self.assertEqual(p.v.commands['4'],dict(action='buy',name='WallUpgradeVoucher1',num=3))
        self.assertEqual(p.v.gold,100);self.assertEqual(p.maintenance_reserved,60)
        self.assertEqual(len(p.state['delivery_orders']['4']),3)
    def test_twenty_gold_can_do_one_front_wall(self):
        p=plan(scenario(gold=20));self.assertTrue(p.procure('4'));self.assertEqual(p.v.commands['4']['num'],1)
    def test_nineteen_gold_cannot_buy(self):
        p=plan(scenario(gold=19));self.assertFalse(p.procure('4'));self.assertEqual(p.v.gold,19)
    def test_reserved_money_cannot_be_reused(self):
        p=plan(scenario(gold=160));p.capital_reserved=150;self.assertFalse(p.procure('4'))
    def test_full_batch_inventory_covers_exactly_three(self):
        q=scenario();q['teamOur']['roles'][3]['backpack']=['WallUpgradeVoucher1']*3;p=plan(q)
        self.assertEqual(sum(n=='WallUpgradeVoucher1' for _,_,n in p.uncovered_capital()),3)
    def test_flank_upgrade_not_retargeted(self):
        q=scenario(wall_level=2);q['teamOur']['roles'][3]['backpack']=['WallUpgradeVoucher1'];q['teamOur']['goldNum']=0
        p=plan(q);self.assertFalse(p.held_delivery('4'))
    def test_deadline_does_not_authorize_unfinishable_delivery(self):
        p=plan(scenario(460));self.assertFalse(p.procure('4'))
    def test_day4_actual_money_complete_six_when_funded(self):
        q=scenario(gold=160);engine=DayEngine(q,seed=38,respawn=False);s=m.GameSession(origin=1)
        for _ in range(70):engine.apply(s.handle(copy.deepcopy(engine.data)))
        p=plan(engine.data);self.assertEqual([m.level_of(w) for w in p.walls[:6]],[2]*6)
        self.assertEqual(engine.rejected,[])

class BaseInsurance(unittest.TestCase):
    def q(self,level=1,hp=None):
        q=staffed(scenario(501,0,(3,3,3),2,14,level))
        q['teamOur']['roles'][3]['backpack']=[f'StationUpgradeVoucher{level}']
        q['teamOur']['roles'][0]['health']=1500*level if hp is None else hp
        return q
    def test_full_health_holds_both_vouchers(self):
        for lv in (1,2):
            p=plan(self.q(lv));self.assertFalse(p.base_policy()['use_now']);self.assertFalse(p.held_delivery('4'))
    def test_exact_fifty_percent_uses(self):
        for lv in (1,2):
            p=plan(self.q(lv,750*lv));self.assertTrue(p.rescue_base());self.assertEqual(p.v.commands['4']['action'],'use')
    def test_one_above_threshold_holds(self):
        for lv in (1,2):self.assertFalse(plan(self.q(lv,750*lv+1)).base_policy()['use_now'])
    def test_no_owned_coupon_no_imaginary_heal(self):
        q=self.q(1,100);q['teamOur']['roles'][3]['backpack']=[];self.assertFalse(plan(q).rescue_base())
    def test_busy_task_owner_not_used(self):
        p=plan(self.q(1,100));p.v.busy.add('4');self.assertFalse(p.rescue_base())
    def test_actual_burst_raises_threshold(self):
        p=plan(self.q(1,1400));q=self.q(1,800);q['roundNo']+=1;p2=plan(q,p.memory)
        self.assertEqual(p2.base_hit,600);self.assertEqual(p2.base_policy()['trigger_hp'],1350);self.assertTrue(p2.base_policy()['use_now'])
    def test_gap_not_a_damage_rate(self):
        p=plan(self.q(1,1400));q=self.q(1,800);q['roundNo']+=2;p2=plan(q,p.memory)
        self.assertEqual(p2.base_policy()['damage_bound'],0);self.assertFalse(p2.base_policy()['use_now'])
    def test_level_change_not_a_damage_observation(self):
        p=plan(self.q(1,1400));q=self.q(2,1000);q['roundNo']+=1;p2=plan(q,p.memory);self.assertEqual(p2.base_hit,0)
    def test_trigger_never_above_ninety_percent(self):
        p=plan(self.q(1,1499));p.state['base_rate_v38']=10000
        self.assertEqual(p.base_policy()['trigger_hp'],1350);self.assertFalse(p.base_policy()['use_now'])
    def test_far_holder_no_teleport(self):
        q=self.q(1,100);q['teamOur']['roles'][3]['pos']=dict(x=24,y=19)
        p=plan(q);self.assertGreater(p.base_policy()['carrier_eta'],3);self.assertFalse(p.rescue_base())
    def test_coupon_is_consumed_and_full_health_observed(self):
        q=self.q(1,750);p=plan(q);self.assertTrue(p.rescue_base());e=DayEngine(q)
        out=m.empty_response();out['roleCommandMap']=p.v.commands;e.apply(out)
        self.assertEqual(e.data['teamOur']['roles'][0]['health'],3000)
        self.assertEqual(e.data['teamOur']['roles'][0]['level'],2)
        self.assertNotIn('StationUpgradeVoucher1',e.data['teamOur']['roles'][3]['backpack'])
    def test_held_insurance_does_not_block_wall_shopping(self):
        q=scenario();q['teamOur']['roles'][3]['backpack']=['StationUpgradeVoucher2'];p=plan(q)
        self.assertTrue(p.held_delivery('4'));self.assertEqual(p.v.commands['4']['name'],'WallUpgradeVoucher1')
    def test_emergency_base_overrides_wall_budget(self):
        q=scenario(gold=150);q['teamOur']['roles'][0]['health']=400;p=plan(q)
        self.assertTrue(p.procure('4',True));self.assertEqual(p.v.commands['4']['name'],'StationUpgradeVoucher2')

class Expansion(unittest.TestCase):
    def test_healthy_wealthy_day4_enables_G18(self):
        p=plan(scenario(391,250,(3,3,3),2));self.assertTrue(p.expansion['enabled']);self.assertEqual(p.wall_target,18)
    def test_249_disables(self):self.assertFalse(plan(scenario(391,249,(3,3,3),2)).expansion['enabled'])
    def test_day3_disables(self):self.assertFalse(plan(scenario(261,1000,(3,3,3),2)).expansion['enabled'])
    def test_night_disables(self):self.assertFalse(plan(scenario(501,1000,(3,3,3),2)).expansion['enabled'])
    def test_19_turn_window_disables(self):self.assertFalse(plan(scenario(442,1000,(3,3,3),2)).expansion['enabled'])
    def test_missing_second_level_wall_disables(self):self.assertFalse(plan(scenario(391,1000,(3,3,3),1)).expansion['enabled'])
    def test_not_three_global_disables(self):self.assertFalse(plan(scenario(391,1000,(3,3,2),2)).expansion['enabled'])
    def test_injured_operator_disables(self):
        q=scenario(391,1000,(3,3,3),2);q['teamOur']['roles'][1]['health']=175;self.assertFalse(plan(q).expansion['enabled'])
    def test_injured_gun_disables(self):
        q=scenario(391,1000,(3,3,3),2);q['teamOur']['roles'][4]['health']=1699;self.assertFalse(plan(q).expansion['enabled'])
    def test_injured_base_disables(self):
        q=scenario(391,1000,(3,3,3),2);q['teamOur']['roles'][0]['health']=2249;self.assertFalse(plan(q).expansion['enabled'])
    def test_claimed_cash_excluded(self):
        p=plan(scenario(391,300,(3,3,3),2));p.capital_reserved=51;self.assertFalse(p.expansion_policy()['enabled'])
    def test_robot_disables(self):
        q=scenario(391,1000,(3,3,3),2);q['robot']['roles']=[dict(role(90,'bossRobot',(20,20),hp=800),targetTeam='challenger')]
        self.assertFalse(plan(q).expansion['enabled'])

class Pressure(unittest.TestCase):
    def test_one_spare_volley_only(self):
        p=plan(pressure_q());self.assertTrue(p.pressure_enemy());self.assertEqual(len(p.v.commands),1)
        self.assertEqual(next(iter(p.v.commands.values()))['targetPos'],[dict(x=28,y=10)]*3)
    def test_own_robot_prevents_pressure(self):
        q=pressure_q();q['robot']['roles']=[dict(role(90,'smallRobot',(40,31),hp=40),targetTeam='challenger')]
        self.assertFalse(plan(q).pressure_enemy())
    def test_foreign_robot_near_base_prevents_pressure(self):
        q=pressure_q();q['robot']['roles']=[dict(role(90,'smallRobot',(15,22),hp=40),targetTeam='defender')]
        self.assertFalse(plan(q).pressure_enemy())
    def test_first_night_spawn_round_not_used(self):
        q=pressure_q();q['roundNo']=461;self.assertFalse(plan(q).pressure_enemy())
    def test_malformed_robot_field_not_clear(self):
        q=pressure_q();q['robot']={};self.assertFalse(plan(q).pressure_enemy())
    def test_three_unconfirmed_probes_stop(self):
        p=plan(pressure_q());p.state['pressure_misses_v38']=3;self.assertFalse(p.pressure_enemy())
    def test_occupied_controllers_not_stolen(self):
        p=plan(pressure_q());p.v.busy.update(p.characters);self.assertFalse(p.pressure_enemy())
    def test_no_daytime_attack(self):
        q=pressure_q();q['roundNo']=391;self.assertFalse(plan(q).pressure_enemy())
    def test_bad_wall_readiness_prevents_pressure(self):
        q=pressure_q();q['teamOur']['roles'][7]['health']=899;self.assertFalse(plan(q).pressure_enemy())
    def test_bad_base_prevents_pressure(self):
        q=pressure_q();q['teamOur']['roles'][0]['health']=2399;self.assertFalse(plan(q).pressure_enemy())
    def test_cooldown_prevents_pressure(self):
        q=pressure_q()
        for r in q['teamOur']['roles']:
            if r['roleType']=='rocket':r['cooldown']=1
        self.assertFalse(plan(q).pressure_enemy())
    def test_explicit_short_range_not_ignored(self):
        q=pressure_q()
        for r in q['teamOur']['roles']:
            if r['roleType']=='rocket':r['attackRange']=2
        p=plan(q);self.assertFalse(p.pressure_enemy());self.assertEqual(p.v.commands,{})
    def test_remote_damage_suspends_empty_night_work(self):
        q=pressure_q();p=plan(q);q['roundNo']+=1;q['teamOur']['roles'][7]['health']-=60
        p2=plan(q,p.memory);self.assertFalse(p2.night_cleared);self.assertEqual(p2.work_turns,0)
        self.assertTrue(any(e['event']=='unexplained_structure_damage' for e in p2.events))
    def test_local_robot_damage_not_attributed_remote(self):
        q=pressure_q();q['robot']['roles']=[dict(role(90,'bossRobot',(13,22),hp=800),targetTeam='challenger')]
        p=plan(q);q['roundNo']+=1;q['robot']['roles']=[];q['teamOur']['roles'][7]['health']-=40
        p2=plan(q,p.memory);self.assertFalse(any(e['event']=='unexplained_structure_damage' for e in p2.events))
    def test_missing_observation_not_remote_damage(self):
        q=pressure_q();p=plan(q);q['roundNo']+=2;q['teamOur']['roles'][7]['health']-=60
        self.assertFalse(any(e['event']=='unexplained_structure_damage' for e in plan(q,p.memory).events))

class ResourceAccess(unittest.TestCase):
    def test_no_mines_downgrades_day1_goal(self):
        q=scenario(1,count=0);q['mapInfo']['zones']=[z for z in q['mapInfo']['zones'] if z['neutralType'] not in m.MINERALS]
        p=plan(q);self.assertTrue(p.resource_access['stone_remote']);self.assertEqual(p.wall_target,6)
    def test_near_stone_restores_goal(self):
        q=scenario(1,count=0);q['mapInfo']['zones']=[z for z in q['mapInfo']['zones'] if z['neutralType']!='stone']
        q['mapInfo']['zones'].append(dict(neutralType='stone',pos=dict(x=5,y=22)))
        self.assertFalse(plan(q).resource_access['stone_remote']);self.assertEqual(plan(q).wall_target,10)
    def test_mine_depletion_only_successful_own_collection(self):
        q=scenario();p=plan(q);cell=next(iter(p.world.zones['stone']));p.memory.previous_actions={'2':dict(action='collect',targetPos=[dict(zip(('x','y'),cell))])}
        q['roundNo']+=1;q['lastRoundRoleActionResults']={'2':True};p2=plan(q,p.memory)
        self.assertEqual(p2.state['mine_used'][('stone',cell)],1)
    def test_failed_collect_does_not_reduce_estimated_stock(self):
        q=scenario();p=plan(q);cell=next(iter(p.world.zones['stone']));p.memory.previous_actions={'2':dict(action='collect',targetPos=[dict(zip(('x','y'),cell))])}
        q['roundNo']+=1;q['lastRoundRoleActionResults']={'2':False};self.assertEqual(plan(q,p.memory).state['mine_used'],{})
    def test_gap_resets_remaining_stock_assumption(self):
        q=scenario();p=plan(q);cell=next(iter(p.world.zones['stone']));p.state['mine_used'][('stone',cell)]=9
        q['roundNo']+=2;self.assertEqual(plan(q,p.memory).state['mine_used'],{})
    def test_disappearing_mine_releases_its_old_counter(self):
        q=scenario();p=plan(q);cell=next(iter(p.world.zones['stone']));p.state['mine_used'][('stone',cell)]=9
        q['mapInfo']['zones']=[z for z in q['mapInfo']['zones'] if (z['pos']['x'],z['pos']['y'])!=cell]
        q['roundNo']+=1;self.assertNotIn(('stone',cell),plan(q,p.memory).state['mine_used'])
    def test_report_lists_actual_policy_not_old_C14_label(self):
        p=plan(scenario());r=p.report();self.assertEqual(r['defense_target']['wall_shape'],'rear_staggered_C14_G18')
        for name in ('base_insurance','resource_access','expansion','front_readiness'):self.assertIn(name,r)


class AccessIntegration(unittest.TestCase):
    def test_emergency_gate_yield_then_real_arrival_then_use(self):
        q=staffed(scenario(501,0,(3,3,3),2,14,1));q['teamOur']['roles'][0]['health']=700
        q['teamOur']['roles'][3].update(pos=dict(x=7,y=22),backpack=['StationUpgradeVoucher1'])
        e=DayEngine(q);memory=None;sequence=[]
        for _ in range(3):
            p=plan(e.data,memory);memory=p.memory;self.assertTrue(p.rescue_base())
            out=m.empty_response();out['roleCommandMap']=p.v.commands;sequence.append(copy.deepcopy(p.v.commands))
            e.apply(out);memory.previous_actions=copy.deepcopy(out['roleCommandMap'])
        self.assertNotIn('4',sequence[0]);self.assertEqual(sequence[1]['4']['action'],'move')
        self.assertEqual(sequence[2]['4']['action'],'use');self.assertEqual(e.data['teamOur']['roles'][0]['health'],3000)
    def test_gated18_build_then_three_operators_actually_return(self):
        q=staffed(scenario(391,1000,(3,3,3),2,14));q['teamOur']['roles'][1]['backpack']=['stone']*5+['Medicine']*2
        for idx in (2,3):q['teamOur']['roles'][idx]['backpack']=['Medicine']*2
        e=DayEngine(q,seed=3801,respawn=False);s=m.GameSession(origin=1)
        for _ in range(70):e.apply(s.handle(copy.deepcopy(e.data)))
        p=plan(e.data);self.assertEqual(len(p.walls),18);self.assertEqual(len(p.matching()),3)
        self.assertNotIn(p.gate_cell,{w['cell'] for w in p.walls});self.assertNotIn(p.service_gate,{w['cell'] for w in p.walls})
    def test_two_calls_cannot_send_two_pressure_volleys_in_one_round(self):
        p=plan(pressure_q());self.assertTrue(p.pressure_enemy());self.assertFalse(p.pressure_enemy());self.assertEqual(len(p.v.commands),1)
    def test_pressure_is_called_on_real_production_path(self):
        q=pressure_q();q['mapInfo']['zones']=[z for z in q['mapInfo']['zones'] if z['neutralType'] not in m.MINERALS]
        for r in q['teamOur']['roles']:
            if r['roleType'] in m.CHARACTERS:r['backpack']=['Medicine']*2+['WallFixer']
        p=plan(q);p.state['siege_alarm_until']=q['roundNo']+12
        out,report=p.run();self.assertEqual(sum(c['action']=='attack' for c in out['roleCommandMap'].values()),1)
        self.assertTrue(any(e['event']=='pressure_probe' for e in report['events']))
    def test_three_actual_unconfirmed_feedbacks_disable_probes(self):
        q=pressure_q();mem=None
        for i in range(3):
            p=plan(q,mem);self.assertTrue(p.pressure_enemy());mem=p.memory
            mem.previous_actions=copy.deepcopy(p.v.commands);q['lastRoundRoleActionResults']={a:True for a in p.v.commands};q['roundNo']+=1
        p=plan(q,mem);self.assertEqual(p.state['pressure_misses_v38'],3);self.assertFalse(p.pressure_enemy())
    def test_pressure_hp_change_is_not_claimed_causal(self):
        q=pressure_q();p=plan(q);p.pressure_enemy();p.memory.previous_actions=copy.deepcopy(p.v.commands)
        q['lastRoundRoleActionResults']={a:True for a in p.v.commands};q['roundNo']+=1;q['teamEnemy']['roles'][1]['health']-=60
        p2=plan(q,p.memory);event=next(e for e in p2.events if e['event']=='pressure_probe_feedback')
        self.assertTrue(event['observed_damage']);self.assertFalse(event['causal_claim'])

if __name__=='__main__':unittest.main()
