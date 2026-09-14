"""Seeded snapshots through one session; robustness, NOT combat simulation.

Usage: python -B tools/fuzz_survival_v31.py --output results.json
"""
from __future__ import annotations
import argparse,json,logging,random,sys,time
from pathlib import Path
from copy import deepcopy


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seed',type=int,default=20260914);ap.add_argument('--steps',type=int,default=600);args=ap.parse_args()
    if not 1 <= args.steps <= 1300:ap.error('--steps must be in 1..1300')
    sys.path.insert(0,str(args.root.resolve()))
    from tests.test_survival_v3 import battle_state,make_role
    from src.agentrace.session import GameSession
    from src.agentrace.model import building_ring
    from tools.simulate_survival import footprint,maxhp
    logging.disable(logging.CRITICAL)
    rng=random.Random(args.seed);s=GameSession(strategy_mode='survival',origin=1)
    errors=[];counts={};start=time.monotonic();previous={};examples=[]
    for r in range(1,args.steps+1):
        data=battle_state(round_no=r,gold=rng.randrange(2001),levels=tuple(rng.randint(1,3) for _ in range(3)))
        roles=data['teamOur']['roles'];taken=set().union(*(footprint(x) for x in roles))
        taken.update((z['pos']['x'],z['pos']['y']) for z in data['mapInfo']['zones'])
        for idx,cell in enumerate(sorted(building_ring((9,22),2))):
            if cell not in taken and rng.random()<0.35:
                wall=make_role(100+idx,'wall',cell,level=rng.randint(1,3));wall['health']=rng.randint(1,maxhp(wall))
                roles.append(wall);taken.add(cell)
        for role in roles:
            if role['roleType'] in {'worker','pioneer'}:
                items=['stone','copper','iron','Medicine','WeaponUpgradeVoucher1','WeaponUpgradeVoucher2','WallUpgradeVoucher1','StationUpgradeVoucher1','StationUpgradeVoucher2','WallFixer']
                n=rng.choice([0,1,2,8,10,role['backPackCapability']])
                role['backpack']=[rng.choice(items) for _ in range(n)]
                role['health']=rng.randint(1,maxhp(role))
            elif role['roleType']=='rocket':role['cooldown']=rng.randrange(4)
        roles[0]['health']=rng.randint(1,maxhp(roles[0]))
        if (r-1)%130>=70:
            for j in range(rng.randrange(21)):
                free=[(x,y) for x in range(5,18) for y in range(14,29) if (x,y) not in taken]
                cell=rng.choice(free);taken.add(cell)
                kind,health=rng.choice([('smallRobot',40),('middleRobot',60),('largeRobot',500),('bossRobot',800)])
                data['robot']['roles'].append(make_role(1000+j,kind,cell,health=rng.randint(1,health),targetTeam='challenger'))
        data['lastRoundRoleActionResults']={a:rng.choice([True,True,True,False]) for a in previous}
        try:
            out=s.handle(deepcopy(data));assert out==s.handle(deepcopy(data)),'duplicate_changed'
            commands=out['roleCommandMap'];controlled=[];destinations=[]
            for a,c in commands.items():
                counts[c['action']]=counts.get(c['action'],0)+1
                if c['action']=='attack':controlled.append(c['controllerId'])
                if c['action']=='move':destinations.append((c['targetPos'][0]['x'],c['targetPos'][0]['y']))
            assert len(controlled)==len(set(controlled)),'controller_conflict'
            assert not(set(controlled)&commands.keys()),'controller_has_second_action'
            assert len(destinations)==len(set(destinations)),'move_target_conflict'
            assert not(set(destinations)&taken),'move_into_occupied'
            previous=commands
        except Exception as exc:
            errors.append(dict(round=r,type=type(exc).__name__,message=str(exc)));examples.append(dict(input=data))
    result=dict(seed=args.seed,steps=args.steps,same_session=True,duplicate_calls=args.steps,exceptions_or_check_failures=errors,actions=counts,
       seconds=time.monotonic()-start,scope='Random valid-shaped snapshots, NOT state transitions or official legality/combat proof. GameSession gate plus independent controller/destination checks.',failure_inputs=examples)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[main]',json.dumps({k:v for k,v in result.items() if k!='failure_inputs'},ensure_ascii=False))
    return bool(errors)

if __name__=='__main__':raise SystemExit(main())
