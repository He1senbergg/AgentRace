"""Supplementary read-only probes for the DeepSeek review."""
from __future__ import annotations
import argparse,json,logging,sys
from pathlib import Path
from copy import deepcopy


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    sys.path.insert(0,str(args.root.resolve()))
    from tests.test_survival_v3 import battle_state,actor,planner,SurvivalNightFirePriorityTests
    from tools.simulate_survival import footprint
    logging.disable(logging.CRITICAL)
    result={}
    data=SurvivalNightFirePriorityTests._night_state(bag=['WeaponUpgradeVoucher1'])
    base=next(r for r in data['teamOur']['roles'] if r['roleType']=='station')
    conflicts=[]
    for role in data['teamOur']['roles']:
        if role is not base and footprint(base)&footprint(role):
            conflicts.append({'station_id':base['id'],'other_id':role['id'],'other_type':role['roleType'],'cells':list(footprint(base)&footprint(role))})
    p=planner(deepcopy(data));result['deepseek_added_night_fixture']={'input':data,'base_overlap':conflicts,'maximum_controller_matching':p.matching()}
    data=battle_state(round_no=71,levels=(2,2,3))
    actor(data,2)['pos']={'x':7,'y':22}
    actor(data,3).update(pos={'x':8,'y':23},backpack=['WeaponUpgradeVoucher2'])
    actor(data,6)['cooldown']=2
    from tools.simulate_survival import make_role
    data['robot']['roles']=[make_role(800,'largeRobot',(14,18),health=500,targetTeam='challenger')]
    p=planner(deepcopy(data));response,report=p.run();actual_response=deepcopy(response)
    legal_alternative=p.v.add('3',dict(action='use',name='WeaponUpgradeVoucher2',targetPos=[dict(x=9,y=23)]))
    result['upgrade_candidate_already_fired']={'input':data,'response':actual_response,'report':report,'alternative_cooldown_upgrade_legal':legal_alternative}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[main] added fixture overlap:',conflicts,'matching:',result['deepseek_added_night_fixture']['maximum_controller_matching'])
    print('[main] cooldown probe:',json.dumps(result['upgrade_candidate_already_fired'],ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
