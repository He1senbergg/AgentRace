"""Independently audit archived round logs, excluding post-collapse fake stalls."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import statistics

ROOT=Path(__file__).resolve().parents[1]


def load_tagged_records(path: Path) -> dict:
    records={'turn':{},'trace_turn':{},'shadow_turn':{}}
    for number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        m=re.search(r'\[(turn|trace_turn|shadow_turn)\] (\{.*\})',line)
        if m:
            data=json.loads(m[2]);records[m[1]][data['round']]=dict(line=number,data=data)
    return records


def audit_match(path: Path) -> dict:
    raw=load_tagged_records(path)
    turns={r:t['data'] for r,t in raw['turn'].items()};shadows={r:t['data'] for r,t in raw['shadow_turn'].items()}
    if not turns:raise ValueError(f'[audit_match] no turn records: {path}')
    dead=min((r for r,s in shadows.items() if not s['metrics']['station_hp']),default=None)
    live={r:t for r,t in turns.items() if dead is None or r<dead}
    actions=Counter();failures=Counter();feedback_seen=Counter();errors=Counter();live_day=Counter()
    for r,t in live.items():
        actions.update(c['action']+(':'+c['name'] if c.get('name') else '') for c in t['actions'])
        errors.update(str(e) for e in t.get('errors',[]))
        if (r-1)%130<70:live_day.update(a['status'] for a in t['activity'])
        if r-1 in turns:
            previous={str(c['id']):c for c in turns[r-1]['actions']}
            for feedback in t.get('feedback') or []:
                action=previous.get(str(feedback['id']))
                if action and type(feedback.get('success')) is bool:
                    name=action['action']+(':'+action['name'] if action.get('name') else '')
                    feedback_seen[name]+=1
                    if feedback['success'] is False:failures[name]+=1
    spend=[r for r,t in live.items() if any(c['action']=='buy' or c['action']=='build' and c.get('name')!='wall' for c in t['actions'])]
    decreases=[r for r,t in live.items() if r-1 in turns and t['gold']<turns[r-1]['gold']]
    segments=[];current=None
    for r,t in sorted(live.items()):
        active=t['task']['active']
        if active and current is None:current=dict(first_active=r,last_active=r,errors=[],prompts=0,commands=0,submissions=0)
        if current is not None:
            current['errors']+=t.get('errors',[])
            if active:
                current['last_active']=r
                current['prompts']+=bool(t['prompt_chars']);current['commands']+=bool(t['execute_chars'])
                current['submissions']+=sum(c['action']=='submitAnswer' for c in t['actions'])
            else:
                current['first_inactive']=r;current['elapsed_observed']=r-current['first_active'];segments.append(current);current=None
    if current:current['first_inactive']=None;current['elapsed_observed']=None;segments.append(current)
    def checkpoint(r):
        if r not in shadows:return None
        m=shadows[r]['metrics']
        return dict(round=r,source_line=raw['shadow_turn'][r]['line'],gold=m['gold'],station_hp=m['station_hp'],
                    walls=m['wall_count'],wall_hp=m.get('wall_total_hp'),weapon_levels=m['weapon_levels'],
                    actors_alive=m['actors_alive'],actors_hp=m['actors_hp'])
    return dict(file=str(path.relative_to(ROOT)),score_from_filename=int(path.stem.rsplit('_',1)[1]),
                unique_turns=len(turns),first_base_absent=dead,live_turns=len(live),
                death_evidence_line=raw['shadow_turn'][dead]['line'] if dead else None,
                last_live_spend_command=max(spend,default=None),last_live_gold_decrease=max(decreases,default=None),
                last_spend_to_base_absent=dead-max(spend) if dead and spend else None,
                checkpoints=[checkpoint(r) for r in (70,130,200,260,330) if checkpoint(r)],
                live_actions=dict(actions),feedback_by_action=dict(feedback_seen),failed_feedback=dict(failures),
                live_error_codes=dict(errors),live_day_activity=dict(live_day),tasks=segments,
                task_protocol_errors=dict(Counter(t['task'].get('protocol_error') for t in live.values() if t['task']['active'] and t['task'].get('protocol_error'))))


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rounds',nargs='*',type=int,default=[5,6,7]);args=p.parse_args()
    results=[]
    for round_no in args.rounds:
        for path in sorted((ROOT/f'log/Versus/round{round_no}').glob('game*/ally*')):
            value=audit_match(path);results.append(value)
            print(f"[main] {path.parent.name}: base_absent={value['first_base_absent']} last_spend={value['last_live_spend_command']} failed_feedback={value['failed_feedback']}",flush=True)
    output=dict(method='Unique [turn] records; command feedback associated only with consecutive previous round. '
                       'Post-base-absence records excluded from economic stall metrics. Scores are filename labels. '
                       'An errorCode=2 or legal submit does not establish full correctness.',matches=results)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
