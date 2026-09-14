from __future__ import annotations
from copy import deepcopy
from collections import Counter
import random,re
from typing import Any
MINERALS={"stone","copper","iron"}
GUNS={"rocket","railgun","gatling"}

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
                    assert (before['roundNo']-1)%130<70,'build_requires_day'
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
                    base_cells=set().union(*(footprint(r) for r in self.data['teamOur']['roles']+self.data.get('teamEnemy',{}).get('roles',[]) if r['roleType']=='station'))
                    free=[(x,y) for x in range(41) for y in range(32) if (x,y) not in blocked and all(dist((x,y),b)>2 for b in base_cells)]
                    if free:
                        q=self.rng.choice(free);self.stock[q]=10
                        self.data['mapInfo']['zones'].append(dict(neutralType=kind,pos=dict(x=q[0],y=q[1])))
        self.data['roundNo']+=1
        self.data['teamOur']['goldNum']=cash+sales+self.rewards.get(self.data['roundNo'],0)
        self.stats['mineral_revenue']+=sales
        self.data['lastRoundRoleActionResults']=feedback
        self.history.append(dict(round=before['roundNo'],gold=before['teamOur']['goldNum'],
             actions=deepcopy(commands),roles=deepcopy(self.data['teamOur']['roles'])))