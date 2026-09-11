"""Day-only controlled replay from Self log map. No combat, tasks or mine respawn.
Usage: python tools/replay_day.py LOG [--source PATH]
"""
import argparse, importlib.util, json, pathlib, re, subprocess, sys
from collections import Counter
ROOT = pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('log');p.add_argument('--source',default='src/main3.py');p.add_argument('--strategy-mode',choices=('legacy','shadow','defense'));a=p.parse_args()
if not __package__:
    raise SystemExit(subprocess.call([sys.executable, '-m', 'tools.replay_day',
                                      str(pathlib.Path(a.log).resolve()), '--source', str(pathlib.Path(a.source).resolve())] + (['--strategy-mode', a.strategy_mode] if a.strategy_mode else []), cwd=ROOT))
if pathlib.Path(a.source).resolve() == ROOT / 'src/main3.py':
    from src import main3 as m
else:
    spec=importlib.util.spec_from_file_location('replay_player',a.source);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
lines=pathlib.Path(a.log).read_text(encoding='utf-8').splitlines()
first=next(json.loads(l.split('[trace_turn] ')[1]) for l in lines if '[trace_turn] ' in l)
map_start=next(i for i,l in enumerate(lines) if '[trace_map] round=1' in l)
zones=[];keys={'s':'stone','i':'iron','c':'copper','V':'vendor','$':'weaponShop'}
for line in lines[map_start+1:map_start+35]:
 match=re.match(r'(\d{2})  (.{41})$',line)
 if match:
  for x,c in enumerate(match[2]):
   if c in keys:zones.append(dict(neutralType=keys[c],pos=dict(x=x,y=int(match[1]))))
roles=[dict(id=r['id'],roleType=r['kind'],pos=dict(zip(('x','y'),r['pos'])),health=r['health'],backpack=[],**({'level':1} if r['kind']=='station' else {})) for r in first['roles']]
data=dict(roundNo=1,teamOur=dict(teamId='replay',type='challenger',goldNum=75,roles=roles),mapInfo=dict(zones=zones),vendorShopList=[dict(name=k,price=v) for k,v in first['vendor_prices'].items()],weaponShopList=[dict(name=k,price=v) for k,v in [('WeaponUpgradeVoucher1',100),('WeaponUpgradeVoucher2',150),('StationUpgradeVoucher1',100),('StationUpgradeVoucher2',150),('WallFixer',10)]])
stock={tuple(z['pos'].values()):10 for z in zones if z['neutralType'] in ('stone','iron','copper')};counts=Counter();gold_earned=0;session=m.GameSession(origin=1, **({'strategy_mode':a.strategy_mode} if a.strategy_mode else {}));next_id=50000
for turn in range(1,71):
 data['roundNo']=turn
 response=session.handle(data);byid={str(r['id']):r for r in roles};feedback={}
 for actor,c in response['roleCommandMap'].items():
  r=byid[actor];action=c['action'];counts[action]+=1;feedback[actor]=True
  if action=='move':r['pos']=c['targetPos'][0]
  elif action=='collect':
   cell=tuple(c['targetPos'][0].values());z=next((z for z in zones if z['pos']==c['targetPos'][0]),None)
   if z is None:feedback[actor]=False;continue
   r['backpack'].append(z['neutralType']);stock[cell]-=1
   if stock[cell]==0:zones.remove(z)
  elif action=='sell':
   price=first['vendor_prices'][c['name']];data['teamOur']['goldNum']+=price*c['num'];gold_earned+=price*c['num']
   for _ in range(c['num']):r['backpack'].remove(c['name'])
  elif action=='build':
   name=c['name'];next_id+=1
   if name=='wall':r['backpack'].remove('stone')
   else:data['teamOur']['goldNum']-=25
   roles.append(dict(id=next_id,roleType=name,pos=c['targetPos'][0],level=1,health=1000,backpack=[]))
  elif action=='buy':
   price=next(x['price'] for x in data['weaponShopList'] if x['name']==c['name']);data['teamOur']['goldNum']-=price*c['num'];r['backpack'] += [c['name']]*c['num']
  elif action=='use':
   r['backpack'].remove(c['name'])
   target=next(x for x in roles if x['pos']==c['targetPos'][0])
   if 'Upgrade' in c['name']:target['level']+=1
   target['health']=1500*target['level'] if target['roleType']=='station' else 500+500*target['level']
 data['lastRoundRoleActionResults']=feedback
print(json.dumps(dict(model='70 rounds; observed initial map; no task income, battle, mine respawn',earned=gold_earned,gold=data['teamOur']['goldNum'],actions=counts,weapons=[(r['roleType'],r['level']) for r in roles if r['roleType'] in ('gatling','railgun','rocket')]),ensure_ascii=True))
