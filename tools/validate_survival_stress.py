"""Long-run economic continuity and dense night decision tests; NOT survival scoring."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
import logging
from pathlib import Path
import random
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.agentrace.session import GameSession
from tools.simulate_survival import DayEngine, generated_observation, make_role, footprint


def economic_continuity(origin: int) -> dict:
    data=generated_observation(9,origin==0);data['roundNo']=origin
    rewards={origin+day*130+19:160 for day in range(10)}
    engine=DayEngine(data,seed=91,rewards=rewards);session=GameSession(strategy_mode='survival',origin=origin)
    checkpoints=[];timings=[]
    for index in range(1300):
        tick=time.perf_counter();out=session.handle(deepcopy(engine.data));timings.append((time.perf_counter()-tick)*1000)
        engine.apply(out)
        if index%130==69:
            roles=engine.data['teamOur']['roles']
            checkpoints.append(dict(day=index//130+1,gold=engine.data['teamOur']['goldNum'],
                walls=sum(r['roleType']=='wall' for r in roles),wall_levels=dict(Counter(r['level'] for r in roles if r['roleType']=='wall')),
                weapon_levels=sorted((r['level'] for r in roles if r['roleType'] in {'rocket','railgun','gatling'}),reverse=True),
                station_levels=[r['level'] for r in roles if r['roleType']=='station']))
    assert not engine.rejected
    assert checkpoints[-1]['weapon_levels']==[3,3,3],checkpoints[-1]
    assert checkpoints[-1]['station_levels']==[3],checkpoints[-1]
    return dict(origin=origin,steps=1300,model='No robots/damage/task grading; 160 exogenous gold each day; NOT 1300-turn survival proof',
                illegal_commands=engine.rejected,stats=dict(engine.stats),day_end=checkpoints,
                mean_ms=statistics.mean(timings),max_ms=max(timings))


def dense_night_cases() -> list:
    cases=[]
    for count in (50,150,350,700):
        for seed in (1,2,3):
            data=generated_observation(seed);data['roundNo']=331
            data['teamOur']['roles']=[make_role(1,'station',(9,22),level=3),
                make_role(2,'worker',(8,23)),make_role(3,'worker',(9,24)),make_role(4,'pioneer',(11,23)),
                make_role(5,'rocket',(8,22),level=3),make_role(6,'rocket',(9,23),level=3),make_role(7,'railgun',(10,23),level=3)]
            blocked={tuple(z['pos'].values()) for z in data['mapInfo']['zones']}
            for role in data['teamOur']['roles']:blocked.update(footprint(role))
            positions=[(x,y) for x in range(41) for y in range(32) if (x,y) not in blocked]
            random.Random(seed).shuffle(positions)
            data['robot']['roles']=[make_role(800+i,'smallRobot' if i%2 else 'largeRobot',cell,health=30 if i%2 else 100,
                                       targetTeam='challenger') for i,cell in enumerate(positions[:count])]
            session=GameSession(strategy_mode='survival',origin=1)
            start=time.perf_counter();out=session.handle(data);elapsed=(time.perf_counter()-start)*1000
            # GameSession has run its independent final ActionValidator gate.
            assert session.handle(deepcopy(data))==out
            controllers=[c['controllerId'] for c in out['roleCommandMap'].values() if c['action']=='attack']
            assert len(controllers)==len(set(controllers))
            assert all(a not in out['roleCommandMap'] for a in controllers)
            cases.append(dict(robots=count,seed=seed,ms=elapsed,commands=len(out['roleCommandMap']),firing_weapons=len(controllers)))
    return cases


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();logging.disable(logging.CRITICAL)
    results=dict(economic_continuity=[],dense_night=[])
    def save():
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for origin in (0,1):
        results['economic_continuity'].append(economic_continuity(origin));save()
        print(f'[main] origin={origin}: 1300 economic continuity steps passed (no combat modeled)',flush=True)
    results['dense_night']=dense_night_cases();save()
    print('[main] dense night decision cases passed: '+str(len(results['dense_night'])),flush=True)

if __name__=='__main__':main()
