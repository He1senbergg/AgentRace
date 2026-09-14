"""Execute actual emitted task commands against independent local fixtures."""
import importlib.util,sys,json,tempfile,subprocess,hashlib,threading,uuid,pickle,re
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
W=Path(__file__).resolve().parents[1]
def load(name,path):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);return m
new=load('candidate_skill',W/'src/main3.py')
old=load('old_page_runner_only',W/'src/main3.py')
old._HERITAGE_RUNNER=(W/'tests_v34/fixtures/v33_page_runner.txt').read_text(encoding='utf-8')
packets=json.loads((W/'tests_v34/fixtures/task_packets.json').read_text(encoding='utf-8'))
results=[]
def record(**d):
 results.append(d);assert d['passed'],d

def execute(command):
 assert command
 return subprocess.run(command.replace('python3 -c ','python3 -S -c ',1),shell=True,capture_output=True,text=True,timeout=15)
for game,r,text,packet in packets:
 if not any(d['path'].endswith('/spec.md') for d in packet['documents']):continue
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);packet=json.loads(json.dumps(packet));brief=packet['documents'][0];parent=Path(brief['path']).parent
  for doc in packet['documents']:
   doc['text']=doc['text'].replace(str(parent),str(root));doc['path']=doc['path'].replace(str(parent),str(root))
   p=Path(doc['path']);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(doc['text'])
  spec=next(d for d in packet['documents'] if d['path'].endswith('/spec.md'));home=Path(spec['path']).parent
  plan=new.parse_deployment_spec(spec['text']);assert plan
  for name,rows in plan['configs'].items():
   p=home/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('wrong\r\n'*max(map(int,rows))).encode())
  for name,mode in plan['scripts']:(home/name).chmod(0o600)
  token='synthetic-current-'+uuid.uuid4().hex
  verifier="import json,os,pathlib,stat\np="+repr(plan)+"\nroot=pathlib.Path('.')\n"
  verifier+="for path,mode in p['directories']:\n assert (root/path).is_dir() and stat.S_IMODE((root/path).stat().st_mode)==mode\n"
  verifier+="for path,rows in p['configs'].items():\n lines=(root/path).read_text().splitlines()\n for n,v in rows.items():assert lines[int(n)-1]==v\n"
  verifier+="for path,mode in p['scripts']:assert stat.S_IMODE((root/path).stat().st_mode)==mode\n"
  verifier+="print('[ OK ] requirements satisfied')\nprint('TOKEN: '+"+repr(token)+")\n"
  import shlex
  checker=home/'check';checker.write_bytes(('#!/bin/sh\npython3 -S -c '+shlex.quote(verifier)+'\n').replace('\n','\r\n').encode());checker.chmod(0o755)
  before=hashlib.sha256(checker.read_bytes()).hexdigest()
  b=execute(new.deployment_repair_command('[exitCode:0]\n'+json.dumps(packet,ensure_ascii=False),text))
  record(case=game+':'+str(r),kind='CRLF_deployment_actual_command',passed=b.returncode==0 and json.loads(b.stdout)=={'token':token} and hashlib.sha256(checker.read_bytes()).hexdigest()==before,error=b.stderr[:300])
print('[test_tasks] CRLF passed',len(results),flush=True)

class API(BaseHTTPRequestHandler):
 mode='offset';queries=[];count=15;key='';location=''
 def log_message(self,*args):pass
 def do_GET(self):
  query=parse_qs(urlparse(self.path).query);API.queries.append(query)
  code=200
  if self.headers.get('Authorization')!='Bearer '+API.key or API.mode=='401':
   code=401;obj={'code':401,'status':'error','message':"Authentication failed: Missing 'Authorization' header. Expected format: 'Authorization: Bearer <api_key>'"}
  elif query.get('location')!=[API.location]:
   code=400;obj={'code':400,'status':'error','message':'Missing required parameter: location'}
  else:
   page=int(query.get('page',['1'])[0]);offset=int(query.get('offset',['0'])[0])
   if API.mode=='page':offset=(page-1)*10
   if API.mode=='repeat':offset=0
   if API.mode=='overlap' and offset:offset-=1
   if API.mode=='fail_page2' and offset:code=500;obj={'code':500,'status':'error','message':'page unavailable'}
   else:
    data=[{'id':'NEW'+str(i),'name':'独立测试记录'+str(i),'type':'建筑' if i%2 else '遗址','era':'旧石器时代' if i==API.count-1 else '明' if i%2 else '元','protected_level':'世界遗产' if i%3==0 else '国家级'} for i in range(API.count)]
    if API.mode=='unknown_era':data[-1]['era']='年代未知'
    meta={'total_count':API.count,'offset':offset,'limit':10}
    if API.mode=='page':meta={'page':page,'total_pages':(API.count+9)//10,'page_size':10,'total_count':API.count}
    if API.mode=='changed_total' and offset:meta['total_count']+=1
    if API.mode=='bad_offset' and offset:meta['offset']=9
    batch=data[offset:offset+10]
    if API.mode=='empty_page2' and offset:batch=[]
    obj={'code':200,'data':{'records':batch,'pagination':meta}}
  raw=json.dumps(obj,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
server=ThreadingHTTPServer(('127.0.0.1',0),API);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 for game,r,text,packet in packets:
  if not any(d['path'].endswith('API_DOCS.md') for d in packet['documents']):continue
  packet=json.loads(json.dumps(packet));API.mode='offset';API.key='current-'+uuid.uuid4().hex
  brief=packet['documents'][0];API.location=re.search(r'"city"\s*:\s*"([^\"]+)"',brief['text'])[1]
  API.count={'北京':15,'南京':12,'成都':10}[API.location]
  for doc in packet['documents']:
   doc['text']=doc['text'].replace('http://localhost:8899','http://127.0.0.1:'+str(server.server_port))
   if doc['path'].endswith('API_DOCS.md'):
    doc['text']=re.sub(r'(\|\s*)`[^`\r\n]+`(\s*\|\s*全量查询权限\s*\|)',lambda m:m[1]+'`'+API.key+'`'+m[2],doc['text'])
  obs='[exitCode:0]\n'+json.dumps(packet,ensure_ascii=False)
  baseline=execute(old.heritage_query_command(obs,text))
  API.queries=[];cmd=new.heritage_query_command(obs,text);b=execute(cmd);value=json.loads(b.stdout) if b.returncode==0 else None
  expected={'city':API.location,'total_count':API.count,'world_heritage_count':len(range(0,API.count,3)),'types':['建筑','遗址'],'oldest_era':'独立测试记录'+str(API.count-1)}
  good=(b.returncode==0 and value==expected and len(API.queries)==(API.count+9)//10)
  record(case=game+':'+str(r),kind='current_docs_actual_offset_contract',passed=good,baseline_returncode=baseline.returncode,baseline_correct=baseline.returncode==0 and json.loads(baseline.stdout)==expected,new_returncode=b.returncode,requests=API.queries,error=b.stderr[:300])
 for mode in ['401','fail_page2','repeat','unknown_era','changed_total','bad_offset','empty_page2','overlap','page']:
  API.mode=mode;API.count=15;API.queries=[]
  b=execute(cmd);good=(b.returncode==0 and json.loads(b.stdout)['total_count']==15) if mode=='page' else b.returncode!=0 and not b.stdout.strip()
  record(case=mode,kind='API_compatibility_or_negative',passed=good,returncode=b.returncode,error=b.stderr[:300])
finally:server.shutdown();server.server_close()
(W/'task_validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('[test_tasks] passed',len(results),'baseline api success',sum(x.get('baseline_correct',False) for x in results),flush=True)
