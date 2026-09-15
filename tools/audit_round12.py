"""Local analysis tool, not part of the platform entry. Never send logs to external services."""
from pathlib import Path
import json,base64,zlib,hashlib,pickle,re,statistics
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]

def decode_log(path):
 groups={};turns={};shadows={};issues=[]
 for ln,line in enumerate(path.open(encoding='utf-8'),1):
  if '[write_task_trace] REPLAY3 ' in line:
   x=json.loads(line.split('REPLAY3 ',1)[1]);key=(x['session'],x['sequence']);g=groups.setdefault(key,{'meta':x,'pieces':{},'lines':[]})
   if x['part'] in g['pieces']:issues.append(['duplicate',ln])
   g['pieces'][x['part']]=x['data'];g['lines'].append(ln)
  elif '[handle] [shadow_turn] ' in line:
   x=json.loads(line.split('[shadow_turn] ',1)[1]);shadows[x['round']]=dict(data=x,line=ln)
  elif '[trace_turn] [turn] ' in line:
   x=json.loads(line.split('[turn] ',1)[1]);turns[x['round']]=dict(data=x,line=ln)
 frames={}
 for g in groups.values():
  x=g['meta'];pieces=g['pieces']
  if set(pieces)!=set(range(1,x['parts']+1)):issues.append(['incomplete',x['round']]);continue
  b=zlib.decompress(base64.b64decode(''.join(pieces[i] for i in range(1,x['parts']+1))))
  if len(b)!=x['raw_bytes'] or hashlib.sha256(b).hexdigest()!=x['sha256']:issues.append(['checksum',x['round']]);continue
  f=json.loads(b);f['_lines']=g['lines'];f['_trace']=turns.get(f['round']);f['_shadow']=shadows.get(f['round']);frames[f['round']]=f
 return frames,issues

def base(q,key):
 return next((r for r in q.get(key,{}).get('roles',[]) if r['roleType']=='station' and r['health']>0),None)

def checkpt(f):
 q=f['request'];rs=q['teamOur']['roles'];b=base(q,'teamOur');side=q['teamOur']['type']
 return dict(round=f['round'],base_hp=b['health'] if b else None,base_level=b.get('level') if b else None,gold=q['teamOur']['goldNum'],request_totalScore=q['teamOur'].get('totalScore'),weapons=[(r['id'],r['level'],r['health'],r['pos']) for r in rs if r['roleType']=='rocket'],walls=[(r['id'],r['level'],r['health'],r['pos']) for r in rs if r['roleType']=='wall'],robots=sum(r.get('targetTeam')==side for r in q['robot']['roles']),line_start=f['_lines'][0])

def audit_round12():
 import argparse
 parser=argparse.ArgumentParser(description='Verify printed REPLAY3 envelopes in local, approved Round12 logs.')
 parser.add_argument('--root',type=Path,default=ROOT)
 parser.add_argument('--out',type=Path,default=ROOT/'runs/round12_integrity.json')
 args=parser.parse_args();rows=[]
 files=sorted(args.root.glob('log/round12/game*/ally*'))
 if not files:raise SystemExit('[audit_round12] no local Round12 ally logs found; no platform filesystem access is expected')
 for path in files:
  frames,issues=decode_log(path)
  rows.append(dict(file=str(path.relative_to(args.root)),frames=len(frames),issues=issues,
                   sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 args.out.parent.mkdir(parents=True,exist_ok=True)
 args.out.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 print('[audit_round12] '+json.dumps(dict(files=len(rows),frames=sum(x['frames'] for x in rows),
         valid=not any(x['issues'] for x in rows),out=str(args.out)),ensure_ascii=False),flush=True)
 return 0 if not any(x['issues'] for x in rows) else 1

if __name__=='__main__':raise SystemExit(audit_round12())
