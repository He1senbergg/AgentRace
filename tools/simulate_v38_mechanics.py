"""Independent damage/geometry and economic state transitions. Not robot AI or win rate."""
from pathlib import Path
import sys,json,copy,hashlib
from v37_support import ROOT,load_source
from economy_engine import DayEngine,dist
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tools')]
from tests_v38.test_policy import scenario,staffed
old=load_source('mechanics_v37',ROOT/'tests/tests_v38/fixtures/baseline_v37.py')
new=load_source('mechanics_v38',ROOT/'src/main3.py')

def planner(mod,q,mem):
    w=mod.World(q);delta=mem.observe(w,q['roundNo']);p=mod.SurvivalPlanner(w,mem,delta,mod.Rules());p.assign_return_slots();return p

def insurance(mod,level,loss):
    q=staffed(scenario(501,0,(3,3,3),2,14,level));q['teamOur']['roles'][3]['backpack']=[f'StationUpgradeVoucher{level}']
    e=DayEngine(q,respawn=False);mem=mod.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1)
    used=[];ticks=0
    for step in range(150):
        p=planner(mod,e.data,mem);before=e.data['teamOur']['roles'][0]['health'];p.held_delivery('4')
        out=mod.empty_response();out['roleCommandMap']=p.v.commands;e.apply(out)
        if any(c['action']=='use' for c in out['roleCommandMap'].values()):used.append(dict(tick=step,health_before=before,health_after=e.data['teamOur']['roles'][0]['health']))
        mem.previous_actions=copy.deepcopy(out['roleCommandMap'])
        e.data['teamOur']['roles'][0]['health']-=loss;ticks+=1
        if e.data['teamOur']['roles'][0]['health']<=0:break
    return dict(level=level,constant_damage_per_tick=loss,ticks_until_zero=ticks,upgrade=used,rejected=e.rejected)

def expansion():
    q=staffed(scenario(391,1000,(3,3,3),2,14));q['teamOur']['roles'][1]['backpack']=['stone']*5+['Medicine']*2
    q['teamOur']['roles'][2]['backpack']=['Medicine']*2;q['teamOur']['roles'][3]['backpack']=['Medicine']*2
    e=DayEngine(q,seed=3801,respawn=False);s=new.GameSession(origin=1);counts=[]
    for _ in range(70):
        out=s.handle(copy.deepcopy(e.data));e.apply(out)
        if any(c.get('action')=='build' for c in out['roleCommandMap'].values()):counts.append([e.data['roundNo']-1,sum(r['roleType']=='wall' for r in e.data['teamOur']['roles'])])
    p=planner(new,e.data,new.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1))
    return dict(final_walls=len(p.walls),gate=p.gate_cell,gate_built=any(w['cell']==p.gate_cell for w in p.walls),
        distinct_current_controllers=len(p.matching()),build_rounds=counts,rejected=e.rejected)

def geometry():
    q=scenario();m=new;w=m.World(q);mem=m.GameMemory((q['teamOur']['teamId'],q['teamOur']['type']),origin=1);p=planner(new,q,mem)
    robots=[(13,y) for y in range(19,25)]
    old_guns=[(8,22),(8,21),(11,22)];new_guns=list(p.weapon_slots[:3])
    return dict(assumption='Static enemy-facing front positions only; range<=3 exposure is potential, not a robot target/damage prediction.',
        robot_front_positions=robots,old_guns=old_guns,new_guns=new_guns,
        old_guns_in_possible_range3=sum(any(dist(g,r)<=3 for r in robots) for g in old_guns),
        new_guns_in_possible_range3=sum(any(dist(g,r)<=3 for r in robots) for g in new_guns),
        all_new_level1_rockets_reach_all_front_positions=all(dist(g,r)<=10 for g in new_guns for r in robots))

if __name__=='__main__':
    rows=[dict(version=label,**insurance(mod,lv,loss)) for label,mod in [('V3.7',old),('V3.8',new)] for lv in (1,2) for loss in (50,100,300)]
    result=dict(scope='Economic placement plus fixed exogenous base damage. No official robot AI, PvP settlement order or match scores modeled.',
        source_sha256=hashlib.sha256((ROOT/'src/main3.py').read_bytes()).hexdigest(),insurance=rows,expansion=expansion(),geometry=geometry())
    (ROOT/'runs/v38/mechanics_simulation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('[simulate_v38_mechanics] '+json.dumps(result,ensure_ascii=False),flush=True)
