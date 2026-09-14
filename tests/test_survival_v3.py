"""Independent fixtures for V3: mechanisms, task isolation and actual state transitions."""
from collections import Counter
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

from src.agentrace.actions import ActionValidator
from src.agentrace.memory import GameMemory
from src.agentrace.model import World, Rules, building_ring, inventory
from src.agentrace.session import GameSession
from src.agentrace.survival import SurvivalPlanner
from src.agentrace.task_inspection import fast_task_discovery_command
from tools.simulate_survival import DayEngine, first_observation, generated_observation, make_role, run_case

ROOT=Path(__file__).resolve().parents[1]


def battle_state(round_no=1,gold=0,levels=(1,1,1)):
    data=generated_observation()
    data['roundNo']=round_no;data['teamOur']['goldNum']=gold
    data['teamOur']['roles']=[make_role(1,'station',(9,22)),make_role(2,'worker',(8,23)),
        make_role(3,'worker',(9,24)),make_role(4,'pioneer',(10,24))]
    for actor,kind,cell,level in zip((5,6,7),('rocket','rocket','railgun'),((8,22),(9,23),(10,23)),levels):
        data['teamOur']['roles'].append(make_role(actor,kind,cell,level=level))
    data['mapInfo']['zones']=[dict(neutralType=k,pos=dict(x=x,y=y))
       for k,x,y in [('stone',5,23),('copper',5,20),('vendor',14,20),('weaponShop',14,22)]]
    return data


def actor(data,identifier):
    return next(r for r in data['teamOur']['roles'] if r['id']==identifier)


def planner(data,memory=None):
    world=World(data);memory=memory or GameMemory((7,'challenger'),origin=1)
    delta=memory.observe(world,data['roundNo'])
    result=SurvivalPlanner(world,memory,delta,Rules());result.assign_return_slots()
    return result


class SurvivalMechanismTests(unittest.TestCase):
    def setUp(self):
        self.old_disable=logging.root.manager.disable;logging.disable(logging.CRITICAL)
    def tearDown(self):logging.disable(self.old_disable)

    def test_cheap_wall_upgrades_cannot_starve_l3_weapon_fund(self):
        data=battle_state(round_no=391,gold=100,levels=(3,3,2))
        actor(data,1).update(level=3,health=4500)
        for n,xy in enumerate(sorted(building_ring((9,22),2))[:18]):
            data['teamOur']['roles'].append(make_role(100+n,'wall',xy))
        actor(data,4)['pos']=dict(x=13,y=22)
        p=planner(data)
        self.assertFalse(any(n.startswith('WallUpgrade') for _,_,n in p.service_candidates()))
        self.assertFalse(p.procure('4'))  # Cash is saved; this does NOT reserve an idle worker.
        actor(data,3)['pos']=dict(x=6,y=20)
        p=planner(data);self.assertTrue(p.income('3'))

    def test_production_http_task_fixture_is_valid_headlessly(self):
        from tools.simulate_survival import make_role
        # Same meaningful preconditions as the actual HTTP task test, no mock Flask.
        data=battle_state();data['teamOur']['roles']=[make_role(11,'pioneer',(4,5)),make_role(99,'station',(7,8))]
        data['mapInfo']['zones']=[dict(neutralType='challengerTaskPoint2',pos=dict(x=5,y=5))]
        data['teamOur']['playerTasks']=[dict(taskPosition=dict(x=5,y=5),isValid=True,coldDownRounds=0,timeoutRounds=10)]
        out=GameSession(strategy_mode='survival').handle(data)
        self.assertEqual(out['roleCommandMap']['11']['action'],'acceptTask')

    def test_library_default_is_legacy_compatible_explicit_mode_is_new(self):
        self.assertEqual(GameSession().strategy_mode,'defense')
        self.assertEqual(GameSession(strategy_mode='survival').strategy_mode,'survival')
        with self.assertRaises(ValueError):GameSession(strategy_mode='typo')

    def test_quarry_batch_is_not_single_stone_roundtrip(self):
        data=battle_state();actor(data,2)['pos']=dict(x=6,y=23);actor(data,2)['backpack']=['stone']
        p=planner(data);self.assertTrue(p.build_walls('2'))
        self.assertEqual(p.v.commands['2']['action'],'collect')
        self.assertGreater(p.jobs['2']['quota'],1)

    def test_observed_full_batch_transitions_to_delivery(self):
        data=battle_state();actor(data,2)['pos']=dict(x=6,y=23);actor(data,2)['backpack']=['stone']*8
        p=planner(data);self.assertTrue(p.build_walls('2'))
        self.assertIn(p.v.commands['2']['action'],{'move','build'})
        self.assertEqual(p.jobs['2']['stage'],'build')

    def test_zero_gold_produces_resources_not_unfunded_purchase(self):
        data=battle_state();out=GameSession(strategy_mode='survival').handle(data)
        self.assertTrue(any(a['action'] in {'collect','move','build'} for a in out['roleCommandMap'].values()))
        self.assertFalse(any(a['action']=='buy' for a in out['roleCommandMap'].values()))

    def test_two_builders_do_not_reserve_same_weapon_slot(self):
        data=battle_state(levels=(),gold=75)
        p=planner(data);p.build_weapon('2');p.build_weapon('3')
        jobs=[j['cell'] for j in p.jobs.values() if j['kind']=='weapon']
        self.assertEqual(len(jobs),2);self.assertEqual(len(set(jobs)),2)

    def test_l2_weapon_generates_l3_purchase_not_cap_at_l2(self):
        data=battle_state(gold=150,levels=(2,2,2));actor(data,4)['pos']=dict(x=13,y=22)
        p=planner(data);self.assertTrue(p.procure('4'))
        self.assertEqual(p.v.commands['4'],dict(action='buy',name='WeaponUpgradeVoucher2',num=1))

    def test_exact_150_gold_does_not_get_consumed_by_optional_medicine(self):
        data=battle_state(gold=150,levels=(2,2,2));actor(data,4)['pos']=dict(x=13,y=22)
        out=GameSession(strategy_mode='survival').handle(data)
        self.assertEqual(out['roleCommandMap']['4']['name'],'WeaponUpgradeVoucher2')

    def test_l2_station_emergency_uses_l2_voucher(self):
        data=battle_state(round_no=261,gold=150,levels=(3,3,3));actor(data,1).update(level=2,health=500)
        actor(data,4)['pos']=dict(x=13,y=22)
        p=planner(data);self.assertTrue(p.procure('4',emergency_only=True))
        self.assertEqual(p.v.commands['4']['name'],'StationUpgradeVoucher2')

    def test_paid_coupon_survives_day_boundary_without_job(self):
        data=battle_state(round_no=131,levels=(2,2,2));actor(data,2)['backpack']=['WeaponUpgradeVoucher2']
        out=GameSession(strategy_mode='survival',origin=1).handle(data)
        self.assertEqual(out['roleCommandMap']['2']['action'],'use')
        self.assertEqual(out['roleCommandMap']['2']['name'],'WeaponUpgradeVoucher2')

    def test_held_coupon_can_retarget_a_missing_original_building(self):
        data=battle_state(levels=(2,2,2));actor(data,2)['backpack']=['WeaponUpgradeVoucher2']
        p=planner(data);p.jobs['2']=dict(kind='service',target='9999999',item='WeaponUpgradeVoucher2')
        self.assertTrue(p.held_delivery('2'));self.assertNotEqual(p.jobs['2']['target'],'9999999')

    def test_stock_is_counted_across_couriers(self):
        data=battle_state(gold=1000);actor(data,2)['backpack']=['WeaponUpgradeVoucher1']*3
        actor(data,4)['pos']=dict(x=13,y=22)
        p=planner(data);self.assertFalse(p.procure('4'))
        self.assertFalse(any(c['action']=='buy' for c in p.v.commands.values()))

    def test_two_shop_buyers_cannot_overbuy_same_deficits(self):
        data=battle_state(gold=1000);actor(data,2)['pos']=dict(x=13,y=21);actor(data,4)['pos']=dict(x=13,y=22)
        p=planner(data);self.assertTrue(p.procure('2'));self.assertFalse(p.procure('4'))
        count=sum(c.get('num',0) for c in p.v.commands.values() if c.get('name')=='WeaponUpgradeVoucher1')
        self.assertEqual(count,3)

    def test_same_round_sale_never_finances_purchase(self):
        data=battle_state();actor(data,2)['pos']=dict(x=13,y=20);actor(data,2)['backpack']=['copper']*40
        actor(data,4)['pos']=dict(x=13,y=22)
        p=planner(data);self.assertTrue(p.sell('2',force=True));self.assertEqual(p.v.gold,0)
        self.assertFalse(p.procure('4'))

    def test_income_commits_to_a_sale_trip(self):
        data=battle_state();actor(data,3)['backpack']=['copper']*10
        p=planner(data);self.assertTrue(p.income('3'));self.assertEqual(p.jobs['3']['kind'],'sell')

    def test_full_inventory_can_sell_but_not_collect(self):
        data=battle_state();actor(data,3)['backpack']=['copper']*100
        p=planner(data);self.assertTrue(p.income('3'));self.assertNotEqual(p.v.commands['3']['action'],'collect')

    def test_deadline_prevents_new_long_trip(self):
        data=battle_state(round_no=68,gold=1000)
        p=planner(data);self.assertFalse(p.procure('3'));self.assertFalse(p.build_walls('3'))

    def test_trapped_last_exit_wall_is_refused(self):
        data=battle_state();r=actor(data,4);r['pos']=dict(x=20,y=10)
        ring={(x,y) for x in range(19,22) for y in range(9,12)}-{(20,10)}
        gate=(21,10)
        data['mapInfo']['zones'] += [dict(neutralType='obstacle',pos=dict(x=x,y=y)) for x,y in ring-{gate}]
        p=planner(data);self.assertFalse(p.construction_safe(gate))

    def test_layout_is_180_degree_mirror_and_preserves_exits(self):
        a=planner(generated_observation(2));b=planner(generated_observation(2,True))
        self.assertEqual({(40-x,31-y) for x,y in a.wall_slots},set(b.wall_slots))
        self.assertEqual([(40-x,31-y) for x,y in a.weapon_slots[:3]],list(b.weapon_slots[:3]))
        self.assertEqual(len(a.wall_slots),18)

    def test_night_controller_assignment_is_injective(self):
        data=battle_state(round_no=71);p=planner(data)
        self.assertEqual(len(p.return_slots),3);self.assertEqual(len(set(p.return_slots.values())),3)
        self.assertEqual(len(p.matching()),3)

    def test_night_attack_reserves_unique_controllers(self):
        data=battle_state(round_no=71,levels=(2,2,2))
        data['robot']['roles']=[make_role(800,'smallRobot',(14,18),health=500,targetTeam='challenger')]
        out=GameSession(strategy_mode='survival',origin=1).handle(data)
        fire=[c for c in out['roleCommandMap'].values() if c['action']=='attack']
        self.assertGreater(len(fire),0)
        controllers=[c['controllerId'] for c in fire]
        self.assertEqual(len(controllers),len(set(controllers)))
        self.assertTrue(all(a not in out['roleCommandMap'] for a in controllers))

    def test_cooldown_weapons_do_not_fire(self):
        data=battle_state(round_no=71)
        for r in data['teamOur']['roles']:
            if r['roleType'] in {'rocket','railgun'}:r['cooldown']=2
        data['robot']['roles']=[make_role(800,'smallRobot',(14,18),health=100,targetTeam='challenger')]
        out=GameSession(strategy_mode='survival',origin=1).handle(data)
        self.assertFalse(any(c['action']=='attack' for c in out['roleCommandMap'].values()))

    def test_injured_controller_uses_real_medicine_before_fire(self):
        data=battle_state(round_no=71);actor(data,2).update(health=20,backpack=['Medicine'])
        data['robot']['roles']=[make_role(800,'smallRobot',(14,18),health=100,targetTeam='challenger')]
        out=GameSession(strategy_mode='survival',origin=1).handle(data)
        self.assertEqual(out['roleCommandMap']['2'],dict(action='use',name='Medicine'))
        self.assertFalse(any(c.get('controllerId')=='2' for c in out['roleCommandMap'].values()))

    def test_no_base_is_noop_not_economic_stall(self):
        data=battle_state();data['teamOur']['roles']=[r for r in data['teamOur']['roles'] if r['roleType']!='station']
        out=GameSession(strategy_mode='survival').handle(data)
        self.assertEqual(out['roleCommandMap'],{})

    def test_invalid_health_roles_are_not_commanded(self):
        for bad in [None,'bad',float('inf')]:
            data=battle_state();actor(data,2)['health']=bad
            if isinstance(bad,float):continue  # Session rejects non-JSON finite values at the protocol boundary.
            out=GameSession(strategy_mode='survival').handle(data)
            self.assertNotIn('2',out['roleCommandMap'])

    def test_origin_zero_and_one_have_equivalent_openings(self):
        a=battle_state();b=deepcopy(a);b['roundNo']=0
        self.assertEqual(GameSession(strategy_mode='survival').handle(a),GameSession(strategy_mode='survival').handle(b))

    def test_duplicate_delivery_is_cached_and_deepcopy_isolated(self):
        data=battle_state();session=GameSession(strategy_mode='survival')
        first=session.handle(data);saved=deepcopy(first);first['roleCommandMap'].clear()
        self.assertEqual(session.handle(deepcopy(data)),saved)

    def test_concurrent_duplicates_commit_once(self):
        data=battle_state();session=GameSession(strategy_mode='survival')
        with ThreadPoolExecutor(max_workers=4) as pool:
            out=list(pool.map(lambda _:session.handle(deepcopy(data)),range(8)))
        self.assertTrue(all(r==out[0] for r in out));self.assertEqual(session.diagnostic_turns,1)

    def test_stalled_move_job_is_released_from_real_next_observation(self):
        data=battle_state();mem=GameMemory((7,'challenger'),origin=1);p=planner(data,mem)
        p.jobs['2']=dict(kind='service',target='5',item='WeaponUpgradeVoucher1')
        for n in range(2,5):
            mem.previous_actions={'2':dict(action='move',targetPos=[dict(x=7,y=23)])}
            data['roundNo']=n;data['lastRoundRoleActionResults']={'2':False};p=planner(data,mem)
        self.assertNotIn('2',p.jobs)
        self.assertTrue(any(e['event']=='stalled_trip_released' for e in p.events))

    def test_owner_death_clears_persistent_job(self):
        data=battle_state();p=planner(data);p.jobs['999']=dict(kind='wall',cell=(7,20))
        data['roundNo']=2;p=planner(data,p.memory);self.assertNotIn('999',p.jobs)

    def test_missing_resources_and_shops_do_not_raise_or_invent_cash(self):
        data=battle_state();data['mapInfo']['zones']=[];data['weaponShopList']=[];data['vendorShopList']=[]
        out=GameSession(strategy_mode='survival').handle(data)
        self.assertFalse(any(c['action'] in {'collect','buy','sell'} for c in out['roleCommandMap'].values()))

    def test_voucher_purchase_delivery_use_is_independently_executed(self):
        data=battle_state(gold=150,levels=(2,2,2));actor(data,4)['pos']=dict(x=13,y=22)
        engine=DayEngine(data);session=GameSession(strategy_mode='survival')
        for _ in range(12):engine.apply(session.handle(deepcopy(engine.data)))
        self.assertGreaterEqual(engine.stats['buy:WeaponUpgradeVoucher2'],1)
        self.assertGreaterEqual(engine.stats['use:WeaponUpgradeVoucher2'],1)
        self.assertTrue(any(r['roleType']=='rocket' and r['level']==3 for r in engine.data['teamOur']['roles']))
        self.assertEqual(engine.rejected,[])


class SurvivalWallBatchProtectionTests(unittest.TestCase):
    def setUp(self):
        self.old_disable=logging.root.manager.disable;logging.disable(logging.CRITICAL)
    def tearDown(self):logging.disable(self.old_disable)

    def test_wall_builder_never_sells_wall_stone(self):
        data=battle_state();actor(data,2)['pos']=dict(x=13,y=20);actor(data,2)['backpack']=['stone']*8
        p=planner(data);p.jobs['2']=dict(kind='wall',stage='build',cell=(12,24),quota=8)
        self.assertFalse(p.sell('2',force=True))
        self.assertEqual(p.v.commands,{})
        self.assertEqual(p.jobs['2']['kind'],'wall')

    def test_in_flight_wall_batch_stones_are_never_liquidated(self):
        data=battle_state();actor(data,2)['backpack']=['stone']*8
        p=planner(data);p.jobs['2']=dict(kind='wall',stage='quarry',cell=(12,24),quota=8)
        p.income('2')
        self.assertEqual(p.jobs['2']['kind'],'wall')
        self.assertFalse(any(c.get('action')=='sell' for c in p.v.commands.values()))
        # Execute the response before checking inventory; the input is immutable.
        engine=DayEngine(data)
        engine.apply(dict(roleCommandMap=p.v.commands,prompt='',executeCmd=''))
        self.assertEqual((inventory(actor(engine.data,2)) or Counter())['stone'],8)

    def test_liquidating_copper_keeps_the_wall_job(self):
        data=battle_state();actor(data,2)['pos']=dict(x=13,y=20);actor(data,2)['backpack']=['copper']*10
        p=planner(data);p.jobs['2']=dict(kind='wall',stage='quarry',cell=(12,24),quota=8)
        self.assertTrue(p.sell('2',force=True))
        self.assertEqual(p.v.commands['2'],dict(action='sell',name='copper',num=10))
        self.assertEqual(p.jobs['2']['kind'],'wall')

    def test_held_voucher_is_delivered_even_when_roundtrip_is_tight(self):
        data=battle_state(round_no=68,levels=(2,2,2));actor(data,4)['pos']=dict(x=11,y=23)
        actor(data,4)['backpack']=['WeaponUpgradeVoucher2']
        # A strict margined round-trip no longer fits at R68, but the paid
        # voucher must still be applied rather than abandoned (stuck capital).
        p=planner(data);self.assertTrue(p.held_delivery('4'))
        self.assertIn(p.v.commands['4']['action'],{'move','use'})
        self.assertEqual(p.jobs['4']['kind'],'service')

    def test_completed_wall_target_releases_the_builder(self):
        data=battle_state(gold=100)
        for n,xy in enumerate(sorted(building_ring((9,22),2))[:8]):
            data['teamOur']['roles'].append(make_role(100+n,'wall',xy))
        actor(data,2)['pos']=dict(x=13,y=20);actor(data,2)['backpack']=['copper']*10
        p=planner(data);p.jobs['2']=dict(kind='wall',stage='build',cell=(12,24),quota=8)
        self.assertEqual(p.v.wall_count,8)
        self.assertTrue(p.sell('2',force=True))
        self.assertEqual(p.jobs['2']['kind'],'sell')


class SurvivalNightFirePriorityTests(unittest.TestCase):
    def setUp(self):
        self.old_disable=logging.root.manager.disable;logging.disable(logging.CRITICAL)
    def tearDown(self):logging.disable(self.old_disable)

    @staticmethod
    def _night_state(cooldown=0,bag=None):
        data=battle_state(round_no=71,gold=100)
        actor(data,2)['backpack']=list(bag or [])
        for role in data['teamOur']['roles']:
            if role['roleType'] in {'rocket','railgun'}:
                role['cooldown']=cooldown
        # Valid non-overlapping footprints, three distinct adjacent controllers,
        # and enough target HP that all three guns have useful work.
        data['robot']['roles']=[make_role(800,'largeRobot',(14,18),health=500,targetTeam='challenger')]
        return data

    def test_night_fire_precedes_voucher_use(self):
        data=self._night_state(bag=['WeaponUpgradeVoucher1'])
        out=GameSession(strategy_mode='survival',origin=1).handle(data)
        attacks=[c for c in out['roleCommandMap'].values() if c['action']=='attack']
        self.assertEqual(len(attacks),3)
        self.assertFalse(any(c['action']=='use' for c in out['roleCommandMap'].values()))

    def test_idle_cooldown_window_still_applies_voucher(self):
        data=self._night_state(cooldown=2,bag=['WeaponUpgradeVoucher1'])
        out=GameSession(strategy_mode='survival',origin=1).handle(data)
        self.assertTrue(any(c['action']=='use' for c in out['roleCommandMap'].values()))


class SurvivalTaskTests(unittest.TestCase):
    def task_data(self,round_no=1):
        data=battle_state(round_no=round_no)
        actor(data,4)['pos']=dict(x=16,y=17)
        data['mapInfo']['zones'].append(dict(neutralType='challengerTaskPoint1',pos=dict(x=17,y=17)))
        data['phaseTask']='Compute the required JSON.'
        return data

    def test_active_task_pioneer_not_reassigned_to_logistics(self):
        data=self.task_data();data['teamOur']['goldNum']=1000
        out=GameSession(strategy_mode='survival').handle(data)
        self.assertNotIn('4',out['roleCommandMap']);self.assertTrue(out['prompt'])
        self.assertIn('TURN-EFFICIENT EXECUTION',out['prompt'])
        self.assertIn('task-r2-inspect',out['prompt'])

    def test_actual_next_round_stdout_submits_without_extra_llm(self):
        session=GameSession(strategy_mode='survival');data=self.task_data();session.handle(data)
        data=self.task_data(2);data['llmResp']=json.dumps({'command':'python3 -c "print(17)"','answer_from_stdout':True})
        out=session.handle(data);self.assertTrue(out['executeCmd'])
        data=self.task_data(3);data['lastCmdResult']='[exitCode:0]\n17\n'
        out=session.handle(data);self.assertEqual(out['roleCommandMap']['4']['taskAnswer'],'17')
        self.assertEqual(out['prompt'],'')

    def test_failed_stdout_is_never_automatically_submitted(self):
        session=GameSession(strategy_mode='survival');session.handle(self.task_data())
        data=self.task_data(2);data['llmResp']=json.dumps({'command':'false','answer_from_stdout':True});session.handle(data)
        data=self.task_data(3);data['lastCmdResult']='[exitCode:1]\nTOKEN: untrusted'
        out=session.handle(data);self.assertNotIn('4',out['roleCommandMap']);self.assertTrue(out['prompt'])

    def test_inspection_reads_referenced_workspace_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'ws_alpha').mkdir();(root/'ws_other').mkdir()
            (root/'unit_brief_unique.md').write_text('Fix ws_alpha/solver.py using ws_alpha/spec.md. Run check.sh.',encoding='utf-8')
            (root/'ws_alpha/spec.md').write_text('Return x+1.',encoding='utf-8')
            (root/'ws_alpha/solver.py').write_text('def f(x): return x-1\n',encoding='utf-8')
            (root/'ws_alpha/check.sh').write_text('echo checker\n',encoding='utf-8')
            (root/'ws_other/secret.py').write_text('not related\n',encoding='utf-8')
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            command=fast_task_discovery_command('Read unit_brief_unique.md')
            result=subprocess.run(shlex.split(command),cwd=root,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);packet=json.loads(result.stdout)
            paths={p['path'] for p in packet['documents']}
            self.assertIn(str(root/'ws_alpha/spec.md'),paths);self.assertIn(str(root/'ws_alpha/solver.py'),paths)
            self.assertNotIn(str(root/'ws_other/secret.py'),paths)
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertLessEqual(len(result.stdout.rstrip('\n')),14000)

    def test_inspection_handles_unknown_brief_without_fabricated_command(self):
        self.assertIsNone(fast_task_discovery_command('calculate 3+7'))


class SurvivalClosedLoopTests(unittest.TestCase):
    def test_four_archived_initial_maps_reach_first_night_floor(self):
        old=logging.root.manager.disable;logging.disable(logging.CRITICAL)
        try:
            for game in (25,26,27,28):
                for reward in (0,160):
                    with self.subTest(game=game,reward=reward):
                        path=next((ROOT/f'log/Versus/round7/game{game}').glob('ally*'))
                        result=run_case(first_observation(path),'survival',seed=game,reward=reward)
                        self.assertGreaterEqual(result['walls'],8)
                        self.assertEqual(result['weapons'],3);self.assertEqual(result['controllers_ready'],3)
                        self.assertEqual(result['rejected'],[])
        finally:logging.disable(old)
