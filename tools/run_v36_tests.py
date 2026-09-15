"""Run current behavior tests, retaining mechanics and replacing two old policies."""
from pathlib import Path
import unittest,sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
REPLACED={
 'test_hot_wall_upgrade_does_not_wait_for_all_guns_level_three':
  'Replaced: capped walls after two global rockets; capital clearwave tests enforce the new ordering.',
 'test_preemptive_stock_two_fixers_bound':
  'Replaced: one pre-completion fixer, two only for a complete level-three battery.'}
REPLACED.update({
 'test_adjacent_emergency_repair_uses_owned_item':'V3.6 requires preserving current ready-gun coverage; replaced by ready/cooldown cases.',
 'test_wall_daily_cash_cap_respected':'Day4+ cap60 plus cap40 per incomplete-battery phase; tested explicitly.',
 'test_wall_level_caps_depend_on_guns_and_day':'Flanks remain level1; front readiness gated by established two-gun core.',
 'test_weapon_goal_beats_even_critical_wall_purchase':'Funded weapons still first; bounded unfunded-gap rescue added and tested.'})
def run_v36_tests():
 loader=unittest.TestLoader();suite=unittest.TestSuite();retired=[]
 for mod in ['tests_v34.test_actions','tests_v34.test_memory','tests_v34.test_world','tests_v34.test_frontline','tests_v35.test_capital_clearwave','tests_v36.test_frontline_survival']:
  pending=list(loader.loadTestsFromName(mod))
  while pending:
   obj=pending.pop(0)
   if isinstance(obj,unittest.TestSuite):pending[:0]=list(obj)
   elif obj._testMethodName in REPLACED:retired.append(dict(test=obj.id(),reason=REPLACED[obj._testMethodName]))
   else:suite.addTest(obj)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 report=dict(run=result.testsRun,failures=[x[0].id() for x in result.failures],errors=[x[0].id() for x in result.errors],replaced_policy_tests=retired,passed=result.wasSuccessful())
 (ROOT/'unit_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print('[run_v36_tests] '+json.dumps(report,ensure_ascii=False),flush=True)
 return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(run_v36_tests())
