"""Current suite + new contracts. Superseded exact policy assertions are disclosed."""
from pathlib import Path
import sys,json,unittest,contextlib,io,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tools')]
from run_v37_tests import REPLACED as PREVIOUS
REPLACED=dict(PREVIOUS)
REPLACED.update({
 'test_c_layout_all_initial_maps_and_free_service':'RearLayout validates staggered rear pads, C14 default, optional G18 and the permanent gate.',
 'test_c14_preserves_opening_front_corners_and_flanks':'First14 retained, four optional rear cells added; RearLayout independently checks both.',
 'test_front_floor_schedule_and_flank_cap':'Day3 three / Day4 six L2 front project; flank cap remains one.',
 'test_healthy_front_cannot_fallback_while_saving_for_weapon':'Finite front readiness project replaces waiting for all three guns at L3.',
 'test_healthy_wall_reserves_next_unobserved_weapon_level':'Mandatory Day4 front floor can precede next gun L3; first global/second L2 preserved.',
 'test_early_four_copper_sale_with_missing_turret':'Sale still four, builder now travels to rear. New replacement preserves no same-turn credit.',
 'test_rebuild_uses_25_not_275_cash':'Old builder adjacent only to removed front site. New rear-adjacent test verifies cost25.',
 'test_c14_and_guns_not_repositioned':'New-match guns intentionally moved rear; existing three guns still never demolished.',
 'test_daily_budget_resets_after_spent_yesterday':'Day4+ cap140 instead60, actual spend and reservations still bounded.',
 'test_daily_spend_and_reservations_still_bounded':'140 daily project cap replaces60; new exact spend/reservation tests.',
 'test_funded_second_gun_keeps_priority':'Day4 six-front-floor takes priority over second L3; second L2 still protected.',
 'test_healthy_front_does_not_drain_gun_savings':'Healthy promised floor no longer starves behind all gun savings.',
 'test_no_lifetime_40_gold_starvation':'Lifetime cap still removed; finite daily cap intentionally raised140.',
 'test_game89_540_cash_counterfactual_rebuilds_when_adjacent':'Old front-adjacent fixture no longer adjacent to rear; replacement verifies legal rear build25.',
})

def run_v38_tests():
    modules=['tests_v34.test_actions','tests_v34.test_memory','tests_v34.test_world','tests_v34.test_frontline',
             'tests_v35.test_capital_clearwave','tests_v36.test_frontline_survival','tests_v37.test_sustainment',
             'tests_v37.test_real_cases','tests_v37.test_closed_loop','tests_v38.test_policy']
    loader=unittest.TestLoader();suite=unittest.TestSuite();retired=[];selected=[]
    for name in modules:
        pending=list(loader.loadTestsFromName(name))
        while pending:
            obj=pending.pop(0)
            if isinstance(obj,unittest.TestSuite):pending[:0]=list(obj);continue
            if obj._testMethodName in REPLACED:
                retired.append(dict(test=obj.id(),reason=REPLACED[obj._testMethodName]));continue
            suite.addTest(obj);selected.append(obj.id())
    capture=io.StringIO()
    with contextlib.redirect_stdout(capture):result=unittest.TextTestRunner(verbosity=2).run(suite)
    out=ROOT/'runs/v38';out.mkdir(parents=True,exist_ok=True)
    (out/'unit_stdout.log').write_text(capture.getvalue(),encoding='utf-8')
    report=dict(runtime=sys.version,source_sha256=hashlib.sha256((ROOT/'src/main3.py').read_bytes()).hexdigest(),
                run=result.testsRun,passed=result.wasSuccessful(),selected=selected,
                failures=[dict(test=x.id(),trace=t) for x,t in result.failures],
                errors=[dict(test=x.id(),trace=t) for x,t in result.errors],replaced_policy_tests=retired)
    (out/'unit_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[run_v38_tests] '+json.dumps({k:report[k] for k in ('run','passed','source_sha256')},ensure_ascii=False),flush=True)
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(run_v38_tests())
