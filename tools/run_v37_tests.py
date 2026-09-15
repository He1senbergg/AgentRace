"""Current contracts, with obsolete V3.6 policy assertions explicitly reported."""
from pathlib import Path
import sys,json,unittest,contextlib,io,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tools')]
from run_v36_tests import REPLACED as OLD_REPLACED
REPLACED=dict(OLD_REPLACED)
REPLACED.update({
 'test_medicine_not_overstocked_on_healthy_courier':'Frontline/previously hit carriers may now hold two, not exactly one; new personal stock ceiling test.',
 'test_stock_deficit_count_not_repeated_per_wall':'Three-kit team ceiling replaces two; pending purchases explicitly counted in new tests.',
 'test_stock_deficit_not_subtracted_twice_in_purchase_coverage':'Three-kit team ceiling replaces two; new stock accounting tests.',
 'test_adjacent_repair_cannot_steal_ready_gunner':'An imminent critical breach may cost ONE volley; noncritical and two-volley denial tested separately.',
 'test_almost_funded_weapon_not_reset_by_maintenance':'Third-gun savings no longer forbid urgent frontline maintenance; second-gun core still protected.',
 'test_critical_front_can_use_bounded_fallback':'Critical front can be a direct priority, not only the previous named fallback event.',
 'test_funded_weapon_precedes_critical_wall':'Critical readiness can precede gun #3; funded core and urgent base explicitly protected.',
 'test_hidden_next_weapon_voucher_still_protected_when_nearly_funded':'Critical front maintenance can precede the third gun; healthy walls still use surplus.',
 'test_no_travelling_repair_during_live_wave':'Bounded cooldown-aware move/use/return replaces unconditional travel prohibition.',
 'test_wall_budget_caps_successful_and_reserved_cash':'Remove lifetime 40-gold cap, retain real daily spend/reservation limit.',
})

def run_v37_tests():
    modules=['tests_v34.test_actions','tests_v34.test_memory','tests_v34.test_world',
             'tests_v34.test_frontline','tests_v35.test_capital_clearwave',
             'tests_v36.test_frontline_survival','tests_v37.test_sustainment',
             'tests_v37.test_real_cases','tests_v37.test_closed_loop']
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
    out=ROOT/'runs/v37';out.mkdir(parents=True,exist_ok=True)
    (out/'unit_stdout.log').write_text(capture.getvalue(),encoding='utf-8')
    report=dict(runtime=sys.version,source_sha256=hashlib.sha256((ROOT/'src/main3.py').read_bytes()).hexdigest(),
                run=result.testsRun,passed=result.wasSuccessful(),selected=selected,
                failures=[dict(test=x.id(),trace=t) for x,t in result.failures],
                errors=[dict(test=x.id(),trace=t) for x,t in result.errors],replaced_policy_tests=retired)
    (out/'unit_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[run_v37_tests] '+json.dumps({k:report[k] for k in ('run','passed','source_sha256')},ensure_ascii=False),flush=True)
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(run_v37_tests())
