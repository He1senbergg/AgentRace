"""Shared local validation helpers. Never imported by the platform payload."""
from pathlib import Path
import importlib.util,sys,copy
ROOT=Path(__file__).resolve().parents[1]
def load_source(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    mod.print_log=lambda*a,**k:None;mod.write_task_trace=lambda*a,**k:None
    mod.GameSession.trace_turn=lambda*a,**k:None
    return mod

def encode(value):
    if isinstance(value,dict):return {'@dict':[[encode(k),encode(v)] for k,v in value.items()]}
    if isinstance(value,tuple):return {'@tuple':[encode(x) for x in value]}
    if isinstance(value,set):return {'@set':[encode(x) for x in sorted(value)]}
    if isinstance(value,list):return [encode(x) for x in value]
    if value.__class__.__name__=='Phase':return {'@phase':[value.day,value.round_in_day]}
    if value is None or type(value) in (str,int,float,bool):return value
    raise TypeError(type(value).__name__)

def decode(value,mod):
    if isinstance(value,list):return [decode(x,mod) for x in value]
    if not isinstance(value,dict):return value
    if set(value)=={'@dict'}:return {decode(k,mod):decode(v,mod) for k,v in value['@dict']}
    if set(value)=={'@tuple'}:return tuple(decode(x,mod) for x in value['@tuple'])
    if set(value)=={'@set'}:return set(decode(x,mod) for x in value['@set'])
    if set(value)=={'@phase'}:return mod.Phase(*value['@phase'])
    raise ValueError('unrecognized fixture marker')

def memory_from_fixture(entry,mod):
    fields=decode(entry['prior_memory'],mod)
    mem=mod.GameMemory(fields['identity'],fields['origin']);mem.__dict__.update(fields)
    return mem

def plan_fixture(entry,mod,request=None):
    mem=memory_from_fixture(entry,mod);q=copy.deepcopy(request or entry['request'])
    world=mod.World(q);delta=mem.observe(world,q['roundNo'])
    p=mod.SurvivalPlanner(world,mem,delta,mod.Rules());p.assign_return_slots()
    return p
