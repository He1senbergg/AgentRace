"""Independent daytime rule-subset simulator, NOT the official game engine.

Sources: repository AI Spec. Inputs: first ASCII map and initial role metadata
from archived matches, or deterministic generated maps. Task rewards are an
explicit exogenous scenario; no task grading/robot AI/official scores are modeled.
Resource respawn is uniformly sampled from free cells (an ASSUMPTION).
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
import logging
from pathlib import Path
import random
import re
import statistics
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.agentrace.session import GameSession

SHOP = {'Medicine':10, 'WallFixer':10, 'WeaponUpgradeVoucher1':100,
        'WeaponUpgradeVoucher2':150, 'StationUpgradeVoucher1':100,
        'StationUpgradeVoucher2':150, 'WallUpgradeVoucher1':20,
        'WallUpgradeVoucher2':30}
MINERALS = {'stone', 'iron', 'copper'}
GUNS = {'rocket', 'gatling', 'railgun'}


def coord(value: dict) -> tuple[int, int]:
    return value['x'], value['y']


def dist(a: tuple, b: tuple) -> int:
    return max(abs(a[0]-b[0]), abs(a[1]-b[1]))


def footprint(role: dict) -> set[tuple]:
    x,y = coord(role['pos'])
    return {(x,y),(x+1,y),(x,y-1),(x+1,y-1)} if role['roleType']=='station' else {(x,y)}


def maxhp(role: dict) -> int:
    kind=role['roleType']; level=role.get('level',1)
    return {'worker':220, 'pioneer':200, 'station':1500*level,
            'wall':(1000,1500,2000)[level-1]}.get(kind,(1000,1500,2000)[level-1])


def make_role(actor: int, kind: str, xy: tuple, **fields: Any) -> dict:
    result=dict(id=actor, roleType=kind, pos=dict(x=xy[0],y=xy[1]), level=1,
                backpack=[], backPackCapability=100 if kind=='worker' else 40 if kind=='pioneer' else 0,
                cooldown=0)
    result.update(fields)
    result.setdefault('health',maxhp(result))
    return result


def first_observation(path: Path) -> dict:
    """Only reconstruct the initial map; never call this a full historical replay."""
    lines=path.read_text(encoding='utf-8').splitlines()
    trace=None; grid={}
    for i,line in enumerate(lines):
        if '[trace_turn] ' in line and trace is None:
            trace=json.loads(line.split('[trace_turn] ',1)[1])
        if '[trace_map] round=1' in line:
            for row in lines[i+1:i+36]:
                match=re.match(r'^(\d{2})  (.{41})$',row)
                if match:grid[int(match[1])]=match[2]
            break
    if trace is None or len(grid)!=32:
        raise ValueError(f'[first_observation] incomplete initial trace: {path}')
    zones=[]; enemy=[]
    lookup={'s':'stone','i':'iron','c':'copper','V':'vendor','$':'weaponShop',
            'T':'taskObstacle','t':'taskObstacle','?':'unknownObstacle'}
    enemybase=[]
    for y,row in grid.items():
        for x,symbol in enumerate(row):
            if symbol in lookup:zones.append(dict(neutralType=lookup[symbol],pos=dict(x=x,y=y)))
            elif symbol=='b':enemybase.append((x,y))
            elif symbol in 'wp':enemy.append(make_role(900000+len(enemy),'worker' if symbol=='w' else 'pioneer',(x,y)))
    if enemybase:enemy.append(make_role(999999,'station',(min(x for x,y in enemybase),max(y for x,y in enemybase))))
    roles=[]
    for r in trace['roles']:
        bag=[name for name,count in r['minerals'].items() for _ in range(count)]
        bag+=['Medicine']*r['medicine']
        roles.append(make_role(int(r['id']),r['kind'],tuple(r['pos']),health=r['health'],
                               backpack=bag,backPackCapability=r['capacity']))
    return dict(roundNo=1, teamOur=dict(teamId=7,type='challenger',goldNum=trace['gold'],roles=roles),
                teamEnemy=dict(teamId=8,type='defender',goldNum=75,roles=enemy),
                mapInfo=dict(zones=zones),robot=dict(roles=[]),
                vendorShopList=[dict(name=m,price=p) for m,p in trace['vendor_prices'].items()],
                weaponShopList=[dict(name=m,price=p) for m,p in SHOP.items()],
                lastRoundRoleActionResults={},phaseTask='',llmResp='',errors=[])


def generated_observation(seed: int=0, mirrored: bool=False) -> dict:
    rng=random.Random(seed)
    roles=[make_role(1,'station',(9,22)),make_role(2,'worker',(9,24)),
           make_role(3,'worker',(10,24)),make_role(4,'pioneer',(8,24))]
    cells=set().union(*(footprint(r) for r in roles));zones=[]
    for kind,xy in [('weaponShop',(25,20)),('vendor',(20,16))]:
        zones.append(dict(neutralType=kind,pos=dict(x=xy[0],y=xy[1])));cells.add(xy)
    for kind,count in [('stone',6),('iron',4),('copper',4)]:
        for _ in range(count):
            while True:
                xy=(rng.randrange(41),rng.randrange(32))
                if xy not in cells and not(7<=xy[0]<=12 and 19<=xy[1]<=25):break
            cells.add(xy);zones.append(dict(neutralType=kind,pos=dict(x=xy[0],y=xy[1])))
    data=dict(roundNo=1,teamOur=dict(teamId=7,type='challenger',goldNum=75,roles=roles),
              teamEnemy=dict(roles=[]),mapInfo=dict(zones=zones),robot=dict(roles=[]),
              vendorShopList=[dict(name=m,price=p) for m,p in [('stone',1),('iron',3),('copper',5)]],
              weaponShopList=[dict(name=m,price=p) for m,p in SHOP.items()],lastRoundRoleActionResults={},
              phaseTask='',llmResp='',errors=[])
    if mirrored:
        for r in data['teamOur']['roles']:
            x,y=coord(r['pos']);r['pos']=dict(x=39-x,y=32-y) if r['roleType']=='station' else dict(x=40-x,y=31-y)
        for z in zones:
            x,y=coord(z['pos']);z['pos']=dict(x=40-x,y=31-y)
    return data


class DayEngine:
    """Small independent transition model. Reject instead of repairing illegal output."""
    def __init__(self,data: dict,seed: int=0,rewards: dict[int,int]|None=None,respawn: bool=True):
        self.data=deepcopy(data);self.rng=random.Random(seed);self.rewards=rewards or {};self.respawn=respawn
        self.stock={coord(z['pos']):10 for z in self.data['mapInfo']['zones'] if z['neutralType'] in MINERALS}
        self.stats=Counter();self.rejected=[];self.history=[];self.next_id=1000000

    def apply(self,response: dict) -> None:
        before=deepcopy(self.data)
        roles={str(r['id']):r for r in self.data['teamOur']['roles']}
        observed={str(r['id']):r for r in before['teamOur']['roles']}
        zones={coord(z['pos']):z['neutralType'] for z in before['mapInfo']['zones']}
        occupied=set(zones)
        for r in before['teamOur']['roles']+before.get('teamEnemy',{}).get('roles',[]):occupied.update(footprint(r))
        prices={r['name']:r['price'] for r in before['weaponShopList']}
        vendor={r['name']:r['price'] for r in before['vendorShopList']}
        commands=response['roleCommandMap'];reserved=set();modified=set();consumed=set();feedback={}
        collected=Counter();cash=before['teamOur']['goldNum'];sales=0
        base=next((r for r in observed.values() if r['roleType']=='station'),None)
        gun_count=sum(r['roleType'] in GUNS for r in observed.values())
        wall_count=sum(r['roleType']=='wall' for r in observed.values())
        for actor,c in commands.items():
            try:
                assert actor in observed and actor not in consumed,'actor_missing_or_busy'
                r=roles[actor]; old=observed[actor];kind=r['roleType'];xy=coord(old['pos']);action=c['action']
                p=coord(c['targetPos'][0]) if c.get('targetPos') else None
                bag=Counter(old['backpack']); near=lambda t:dist(xy,t)<=1
                if action=='move':
                    assert kind in {'worker','pioneer'} and dist(xy,p)==1,'move_geometry'
                    assert 0<=p[0]<41 and 0<=p[1]<32 and p not in occupied|reserved,'move_blocked'
                    r['pos']=dict(x=p[0],y=p[1]);reserved.add(p)
                elif action=='collect':
                    assert kind=='worker' and near(p) and zones.get(p) in MINERALS and self.stock.get(p,0)>0,'collect_geometry'
                    assert len(old['backpack'])<old['backPackCapability'],'collect_capacity'
                    r['backpack'].append(zones[p]);collected[p]+=1
                elif action=='build':
                    assert kind=='worker' and near(p) and base is not None,'build_actor'
                    assert p not in occupied|reserved and 0<=p[0]<41 and 0<=p[1]<32,'build_occupancy'
                    name=c['name']; radius=min(dist(p,t) for t in footprint(base))
                    if name=='wall':
                        assert radius==2 and bag['stone']>=1 and wall_count<20,'wall_cost_ring_limit'
                        r['backpack'].remove('stone');wall_count+=1
                    else:
                        assert name in GUNS and radius==1 and cash>=25 and gun_count<3,'gun_cost_ring_limit'
                        cash-=25;gun_count+=1
                    self.data['teamOur']['roles'].append(make_role(self.next_id,name,p));self.next_id+=1
                    reserved.add(p)
                elif action in {'buy','sell'}:
                    store='weaponShop' if action=='buy' else 'vendor'
                    assert kind in {'worker','pioneer'} and any(near(t) and k==store for t,k in zones.items()),'trade_location'
                    num=c['num'];name=c['name'];assert type(num) is int and num>0,'trade_count'
                    if action=='buy':
                        assert name in prices and prices[name]*num<=cash and len(old['backpack'])+num<=old['backPackCapability'],'buy_funds_capacity'
                        cash-=prices[name]*num;r['backpack'] += [name]*num
                    else:
                        assert name in MINERALS and name in vendor and bag[name]>=num,'sale_inventory'
                        for _ in range(num):r['backpack'].remove(name)
                        sales+=vendor[name]*num
                elif action=='use':
                    name=c['name']; assert bag[name]>=1,'use_not_owned'
                    if name=='Medicine':
                        assert p is None,'medicine_self'
                        r['health']=maxhp(r)
                    else:
                        target=next((t for t in roles.values() if coord(t['pos'])==p and t['roleType'] not in {'worker','pioneer'}),None)
                        assert target is not None and near(p) and str(target['id']) not in modified,'use_target'
                        if name=='WallFixer':assert target['roleType']=='wall','fix_wall'
                        else:
                            match=re.fullmatch(r'(Weapon|Station|Wall)UpgradeVoucher([12])',name)
                            assert match and target['level']==int(match[2]),'upgrade_level'
                            assert target['roleType'] in {'Weapon':GUNS,'Station':{'station'},'Wall':{'wall'}}[match[1]],'upgrade_type'
                            target['level']+=1
                        target['health']=maxhp(target);modified.add(str(target['id']))
                    r['backpack'].remove(name)
                else:raise AssertionError('not_modeled_action:'+action)
                consumed.add(actor);feedback[actor]=True
                self.stats[action]+=1
                if 'name' in c:self.stats[action+':'+c['name']]+=c.get('num',1)
            except (AssertionError,KeyError,TypeError,ValueError) as exc:
                self.rejected.append(dict(round=before['roundNo'],actor=actor,command=c,reason=str(exc)))
                raise AssertionError(f'[DayEngine.apply] {self.rejected[-1]}') from exc
        # Shared last harvest: all legal same-round miners receive one item.
        for p,n in collected.items():
            self.stock[p]-=n
            if self.stock[p]<=0:
                kind=zones[p]
                self.data['mapInfo']['zones']=[z for z in self.data['mapInfo']['zones'] if coord(z['pos'])!=p]
                del self.stock[p]
                if self.respawn:
                    blocked={coord(z['pos']) for z in self.data['mapInfo']['zones']}
                    for r in self.data['teamOur']['roles']+self.data.get('teamEnemy',{}).get('roles',[]):blocked.update(footprint(r))
                    free=[(x,y) for x in range(41) for y in range(32) if (x,y) not in blocked]
                    if free:
                        q=self.rng.choice(free);self.stock[q]=10
                        self.data['mapInfo']['zones'].append(dict(neutralType=kind,pos=dict(x=q[0],y=q[1])))
        self.data['roundNo']+=1
        self.data['teamOur']['goldNum']=cash+sales+self.rewards.get(self.data['roundNo'],0)
        self.stats['mineral_revenue']+=sales
        self.data['lastRoundRoleActionResults']=feedback
        self.history.append(dict(round=before['roundNo'],gold=before['teamOur']['goldNum'],
             actions=deepcopy(commands),roles=deepcopy(self.data['teamOur']['roles'])))


def run_case(data: dict,mode: str,seed: int=0,reward: int=0,turns: int=70,details: bool=False) -> dict:
    engine=DayEngine(data,seed,{20:reward} if reward else {})
    session=GameSession(strategy_mode=mode,origin=1 if data['roundNo']!=0 else 0)
    timing=[]
    for _ in range(turns):
        start=time.perf_counter();response=session.handle(deepcopy(engine.data));timing.append((time.perf_counter()-start)*1000)
        engine.apply(response)
    roles=engine.data['teamOur']['roles'];chars=[r for r in roles if r['roleType'] in {'worker','pioneer'}]
    guns=[r for r in roles if r['roleType'] in GUNS]
    # Exhaustive matching independent from production implementation.
    def match(i: int,used: set) -> int:
        if i==len(guns):return 0
        return max([match(i+1,used)]+[1+match(i+1,used|{str(c['id'])}) for c in chars
                   if str(c['id']) not in used and dist(coord(c['pos']),coord(guns[i]['pos']))<=1])
    result=dict(mode=mode,seed=seed,exogenous_reward=reward,turns=turns,
           walls=sum(r['roleType']=='wall' for r in roles),weapons=len(guns),
           weapon_levels=sorted((r['level'] for r in guns),reverse=True),
           controllers_ready=match(0,set()),gold=engine.data['teamOur']['goldNum'],
           stats=dict(engine.stats),rejected=engine.rejected,
           timing_ms=dict(mean=statistics.mean(timing),max=max(timing),p95=sorted(timing)[int(.95*(len(timing)-1))]))
    if details:result['history']=engine.history
    return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--generated',type=int,default=0)
    parser.add_argument('--games',nargs='*',type=int,default=[25,26,27,28])
    parser.add_argument('--rewards',nargs='*',type=int,default=[0,160])
    parser.add_argument('--modes',nargs='*',default=['defense','survival'])
    args=parser.parse_args();logging.disable(logging.CRITICAL)
    cases=[]
    for game in args.games:
        path=next((ROOT/f'log/Versus/round7/game{game}').glob('ally*'))
        cases.append((f'game{game}_initial_map',first_observation(path),game))
    for seed in range(args.generated):cases.append((f'generated_{seed}',generated_observation(seed,seed%2==1),seed))
    results=[]
    for name,data,seed in cases:
        for reward in args.rewards:
            for mode in args.modes:
                result=run_case(data,mode,seed,reward);result['case']=name;results.append(result)
                print(f"[main] {name} reward={reward} {mode}: walls={result['walls']} guns={result['weapon_levels']} controllers={result['controllers_ready']}",flush=True)
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(dict(model='daytime_rule_subset_NOT_official_engine',
                    assumptions=['No tasks, robot damage or official scoring.','Reward, if set, arrives exogenously at round 20.',
                                 'Mines have 10 harvests, then respawn uniformly on an unoccupied cell.',
                                 'Initial task-point symbols remain obstacles, not reconstructed task metadata.'],
                    results=results),ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
