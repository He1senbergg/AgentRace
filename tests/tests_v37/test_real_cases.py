"""Actual Round13 states. Old-state probes are not counterfactual match scores."""
import json,copy,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from v37_support import load_source,plan_fixture
m=load_source('real_cases_v37',ROOT/'src/main3.py')
CASES=json.loads((ROOT/'tests/tests_v37/fixtures/round13_cases.json').read_text())
def case(game,n):return CASES['games'][game][str(n)]

class RealCases(unittest.TestCase):
 def test_game79_488_exit_is_actual_legal_lower_pressure(self):
  p=plan_fixture(case('game79',488),m);response,_=p.run();c=response['roleCommandMap']['10010']
  self.assertEqual(c['action'],'move');cell=m.position(c['targetPos'][0]);self.assertNotIn(cell,p.world.occupied)
  self.assertLess(p.defense.exposure(cell),p.defense.exposure(p.characters['10010']['cell']))
 def test_game79_675_shop_buys_support(self):
  p=plan_fixture(case('game79',675),m);response,_=p.run();c=response['roleCommandMap'].get('10011',{})
  self.assertEqual(c.get('action'),'buy');self.assertIn(c['name'],('Medicine','WallFixer','WallUpgradeVoucher1'))
 def test_game79_690_shop_not_idle(self):
  p=plan_fixture(case('game79',690),m);response,_=p.run();c=response['roleCommandMap'].get('10011',{})
  self.assertEqual(c.get('action'),'buy');self.assertIn(c['name'],('Medicine','WallFixer','WallUpgradeVoucher1'))
 def test_game79_700_no_overdue_shop_detour(self):
  p=plan_fixture(case('game79',700),m);response,_=p.run()
  self.assertFalse(any(c['action']=='buy' for c in response['roleCommandMap'].values()))
 def test_game89_521_copper_sale_trip_is_started(self):
  p=plan_fixture(case('game89',521),m);response,r=p.run()
  self.assertIn('recovery_cash_sale',r['decisions'].values())
  self.assertEqual(r['sustainment']['recovery']['cash_gap'],12)
  self.assertGreaterEqual(r['sustainment']['recovery']['inventory_value'],12)
 def test_game89_540_cash_counterfactual_rebuilds_when_adjacent(self):
  entry=case('game89',540);q=copy.deepcopy(entry['request']);q['teamOur']['goldNum']=33
  p=plan_fixture(entry,m,q);response,_=p.run()
  self.assertTrue(any(c['action']=='build' and c.get('name')=='rocket' and m.position(c['targetPos'][0])==(29,9) for c in response['roleCommandMap'].values()))
 def test_game89_572_late_cash_not_teleported_to_build_pad(self):
  p=plan_fixture(case('game89',572),m);response,_=p.run()
  self.assertFalse(any(c['action']=='build' and c.get('name')=='rocket' for c in response['roleCommandMap'].values()))

def make_full_health_test(event):
 def run(self):
  entry=case('game'+str(event['game']),event['round']);p=plan_fixture(entry,m)
  self.assertEqual(p.characters[event['actor']]['health'],m.max_health(p.characters[event['actor']]))
  response,_=p.run();c=response['roleCommandMap'].get(event['actor'],{})
  self.assertNotEqual((c.get('action'),c.get('name')),('use','Medicine'))
 return run
for event in CASES['full_health_events']:
 setattr(RealCases,'test_full_hp_game%d_round%d_%s'%(event['game'],event['round'],event['actor']),make_full_health_test(event))
