"""Independent DeepSeek patch review. Reads repo only; emits reproducible evidence.
Usage: python -B review_cases.py /path/to/AgentRace --output results.json
No official combat model. The multi-turn checks use the repo's DayEngine.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import logging
from pathlib import Path
import sys


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root',type=Path);ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args();root=args.root.resolve();sys.path.insert(0,str(root))
    from tests.test_survival_v3 import battle_state, actor, planner, make_role
    from src.agentrace.session import GameSession
    from src.agentrace.model import inventory
    from tools.simulate_survival import DayEngine
    logging.disable(logging.CRITICAL)
    result={'python':sys.version,'source_sha256':hashlib.sha256((root/'src/agentrace/survival.py').read_bytes()).hexdigest(),'cases':{}}
    # Full bag of sellable non-construction resources. No injected job required.
    data=battle_state(round_no=131,gold=0)
    actor(data,2).update(pos=dict(x=13,y=20),backpack=['copper']*100)
    p=planner(deepcopy(data));out,report=p.run()
    result['cases']['full_copper_bag_first_turn']={'input':data,'response':out,'report':report}
    engine=DayEngine(data,respawn=True);session=GameSession(strategy_mode='survival',origin=1)
    samples=[]
    for _ in range(260):
        old=deepcopy(engine.data);out=session.handle(deepcopy(old));engine.apply(out)
        if old['roundNo'] in (131,132,140,160,180,195,200,201,260,261,280,310,330,390):
            samples.append({'round':old['roundNo'],'commands':out['roleCommandMap'],
              'worker2_bag':dict(Counter(actor(engine.data,2)['backpack'])),
              'worker2_pos':actor(engine.data,2)['pos'],'worker2_job':deepcopy(session.memory.survival['jobs'].get('2')),
              'wall_count':sum(r['roleType']=='wall' for r in engine.data['teamOur']['roles'])})
    result['cases']['full_copper_bag_260_steps']={'steps':260,'initial':data,'snapshots':samples,
        'worker2_sales':[h['round'] for h in engine.history if h['actions'].get('2',{}).get('action')=='sell'],
        'worker2_final_bag':dict(Counter(actor(engine.data,2)['backpack'])),
        'final_wall_count':sum(r['roleType']=='wall' for r in engine.data['teamOur']['roles']),
        'rejected':engine.rejected,'stats':dict(engine.stats)}
    # A saved wall job is overwritten by income() even though the immediate sale was blocked.
    data=battle_state();actor(data,2).update(pos=dict(x=13,y=20),backpack=['stone']*8)
    p=planner(deepcopy(data));p.jobs['2']=dict(kind='wall',stage='build',quota=8,cell=p.wall_slots[0])
    before=deepcopy(p.jobs);p.income('2')
    middle={'jobs':deepcopy(p.jobs),'commands':deepcopy(p.v.commands)}
    # Second call on the same original geometry with saved changed job: explicit helper chain.
    q=planner(deepcopy(data));q.jobs.update(deepcopy(p.jobs));sold=q.sell('2',force=True)
    result['cases']['wall_protection_lost_after_income']={'input':data,'before_jobs':before,
          'after_income':middle,'next_forced_sell':sold,'next_commands':deepcopy(q.v.commands),
          'scope':'helper composition, not a full GameSession replay'}
    # Emergency upgrade suppression, while ordinary fire remains available.
    data=battle_state(round_no=71,levels=(2,2,2));actor(data,1)['health']=1
    actor(data,2)['backpack']=['StationUpgradeVoucher1']
    data['robot']['roles']=[make_role(800,'largeRobot',(12,20),health=500,targetTeam='challenger')]
    p=planner(deepcopy(data));can_rescue=p.v.add('2',dict(action='use',name='StationUpgradeVoucher1',targetPos=[dict(x=9,y=22)]))
    p=planner(deepcopy(data));out,report=p.run()
    actual=GameSession(strategy_mode='survival',origin=1).handle(deepcopy(data))
    result['cases']['station_health_1_rescue']={'input':data,'rescue_command_is_legal':can_rescue,
           'response':actual,'report':report,'attack_count':sum(c['action']=='attack' for c in actual['roleCommandMap'].values()),
           'station_upgrade_used':any(c.get('name')=='StationUpgradeVoucher1' and c['action']=='use' for c in actual['roleCommandMap'].values())}
    # Last daylight tick: carrier starts as a valid controller but walks to a wall.
    data=battle_state(round_no=70,levels=(2,2,2));actor(data,2)['backpack']=['WallUpgradeVoucher1']
    data['teamOur']['roles'].append(make_role(100,'wall',(12,24)))
    p=planner(deepcopy(data));before={'matching':p.matching(),'slots':p.return_slots,'return_due':p.return_due('2'),'return_cost':p.return_cost('2')}
    engine=DayEngine(data);session=GameSession(strategy_mode='survival',origin=1)
    out=session.handle(deepcopy(data));engine.apply(out)
    after=deepcopy(engine.data);after['robot']['roles']=[make_role(800,'largeRobot',(14,18),health=500,targetTeam='challenger')]
    p=planner(deepcopy(after));after_info={'matching':p.matching(),'positions':{a:c['cell'] for a,c in p.characters.items()}}
    night=session.handle(deepcopy(after))
    result['cases']['day70_wall_trip_vs_return']={'input':data,'before':before,'day_response':out,
       'after':after_info,'night_response':night,'night_attack_count':sum(c['action']=='attack' for c in night['roleCommandMap'].values()),
       'scope':'day movement simulated; next-night decision only, no damage simulation'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for key,value in result['cases'].items():
        print('[main]',key, json.dumps({k:v for k,v in value.items() if k in {'response','worker2_sales','worker2_final_bag','final_wall_count','next_forced_sell','next_commands','attack_count','station_upgrade_used','before','day_response','after','night_attack_count'}},ensure_ascii=False))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
