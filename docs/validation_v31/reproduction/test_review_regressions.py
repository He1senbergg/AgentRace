"""Additional behavioral acceptance checks, separate from uploaded production code.
Usage: python -B test_review_regressions.py /path/to/AgentRace --json results.json
A failing test is a review finding, not an official-judge result.
"""
from __future__ import annotations
import argparse,json,logging,sys,unittest
from copy import deepcopy
from pathlib import Path


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('root',type=Path);ap.add_argument('--json',type=Path,required=True)
    args=ap.parse_args();sys.path.insert(0,str(args.root.resolve()))
    from tests.test_survival_v3 import battle_state,actor,planner,make_role,SurvivalNightFirePriorityTests
    from src.agentrace.session import GameSession
    from tools.simulate_survival import DayEngine,footprint
    logging.disable(logging.CRITICAL)

    class ReviewChecks(unittest.TestCase):
        def test_01_reserved_wall_stone_not_sold(self):
            data=battle_state();actor(data,2).update(pos={'x':13,'y':20},backpack=['stone']*8)
            p=planner(data);p.jobs['2']=dict(kind='wall',stage='build',quota=8,cell=p.wall_slots[0])
            self.assertFalse(p.sell('2',force=True))
            self.assertEqual(p.jobs['2']['kind'],'wall')

        def test_02_dual_weapon_vouchers_do_not_steal_three_ready_guns(self):
            data=battle_state(round_no=71,levels=(2,2,2))
            for a in (2,3):actor(data,a)['backpack']=['WeaponUpgradeVoucher2']
            data['robot']['roles']=[make_role(800,'largeRobot',(14,18),health=500,targetTeam='challenger')]
            out=GameSession(strategy_mode='survival',origin=1).handle(data)
            self.assertEqual(sum(c['action']=='attack' for c in out['roleCommandMap'].values()),3)

        def test_03_adjacent_paid_voucher_may_be_used_on_day70(self):
            data=battle_state(round_no=70,levels=(2,2,2));actor(data,2)['backpack']=['WeaponUpgradeVoucher2']
            p=planner(data);self.assertTrue(p.held_delivery('2'))
            self.assertEqual(p.v.commands['2']['action'],'use')

        def test_04_full_nonstone_bag_can_be_sold_before_quarrying(self):
            data=battle_state(round_no=131);actor(data,2).update(pos={'x':13,'y':20},backpack=['copper']*100)
            out=GameSession(strategy_mode='survival',origin=1).handle(data)
            self.assertEqual(out['roleCommandMap'].get('2'),{'action':'sell','name':'copper','num':100},
                             'Builder must not lock a full bag of unreserved copper behind a wall job.')

        def test_05_day70_nonurgent_wall_errand_preserves_three_controllers(self):
            data=battle_state(round_no=70,levels=(2,2,2));actor(data,2)['backpack']=['WallUpgradeVoucher1']
            data['teamOur']['roles'].append(make_role(100,'wall',(12,24)))
            p=planner(deepcopy(data));self.assertEqual(len(p.matching()),3);self.assertTrue(p.return_due('2'))
            engine=DayEngine(data);session=GameSession(strategy_mode='survival',origin=1)
            engine.apply(session.handle(deepcopy(data)))
            self.assertEqual(len(planner(deepcopy(engine.data)).matching()),3,
                             'Nonurgent wall upgrade must not sacrifice a ready opening-night controller.')

        def test_06_critical_base_retains_legal_rescue_upgrade(self):
            data=battle_state(round_no=71,levels=(2,2,2));actor(data,1)['health']=1
            actor(data,2)['backpack']=['StationUpgradeVoucher1']
            data['robot']['roles']=[make_role(800,'largeRobot',(12,20),health=500,targetTeam='challenger')]
            out=GameSession(strategy_mode='survival',origin=1).handle(data)
            self.assertTrue(any(c['action']=='use' and c.get('name')=='StationUpgradeVoucher1' for c in out['roleCommandMap'].values()),
                            'The old legal base rescue is no longer attempted; damage/target selection not simulated.')

        def test_07_idle_courier_skips_fired_gun_and_upgrades_cooling_gun(self):
            data=battle_state(round_no=71,levels=(2,2,3));actor(data,2)['pos']={'x':7,'y':22}
            actor(data,3).update(pos={'x':8,'y':23},backpack=['WeaponUpgradeVoucher2'])
            actor(data,6)['cooldown']=2
            data['robot']['roles']=[make_role(800,'largeRobot',(14,18),health=500,targetTeam='challenger')]
            out=GameSession(strategy_mode='survival',origin=1).handle(data)
            self.assertEqual(out['roleCommandMap'].get('3'),{'action':'use','name':'WeaponUpgradeVoucher2','targetPos':[{'x':9,'y':23}]},
                             'An already-fired target must not hide another legal cooling-weapon upgrade.')

        def test_08_added_night_fixture_has_valid_building_footprints(self):
            data=SurvivalNightFirePriorityTests._night_state(bag=['WeaponUpgradeVoucher1'])
            base=next(r for r in data['teamOur']['roles'] if r['roleType']=='station')
            conflicts=[r['id'] for r in data['teamOur']['roles'] if r is not base and footprint(r)&footprint(base)]
            self.assertEqual(conflicts,[],'Two test weapons occupy the station footprint.')

    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReviewChecks)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    value=dict(tests=result.testsRun,failures=[{'test':str(t),'traceback':trace} for t,trace in result.failures],
               errors=[{'test':str(t),'traceback':trace} for t,trace in result.errors],skipped=result.skipped,
               passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
               scope='Behavioral review assertions including one fixture-validity check; failures intentionally retained.')
    args.json.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
