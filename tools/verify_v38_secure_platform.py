"""Real TCP tests against exactly the single-file platform payload."""
from pathlib import Path
import tempfile,subprocess,socket,threading,queue,json,time,hashlib,base64,zlib,os,sys,ast,http.client
W=Path(__file__).resolve().parents[1];source=W/'AgentRace_Submission/main3.py'
results=[]
def record(name,condition):
 assert condition,name
 results.append({'case':name,'passed':True})
text=source.read_text();ast.parse(text,feature_version=(3,11));record('Python_3_11_syntax',True)
imports=[n.module.split('.')[0] for n in ast.walk(ast.parse(text)) if isinstance(n,ast.ImportFrom) and n.module]+[a.name.split('.')[0] for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Import) for a in n.names]
record('only_stdlib_imports',all(n in sys.stdlib_module_names for n in imports))
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);(root/'main3.py').write_bytes(source.read_bytes())
 sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
 process=subprocess.Popen([sys.executable,'-S','-B',str(root/'main3.py'),str(port)],cwd=root,env={'PATH':os.defpath},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
 lines=[];ready=threading.Event()
 def drain():
  for line in process.stdout:
   lines.append(line)
   if '[main] HTTP ready' in line:ready.set()
 t=threading.Thread(target=drain,daemon=True);t.start()
 try:
  deadline=time.monotonic()+10
  listening=False
  while time.monotonic()<deadline:
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):listening=True
    break
   except OSError:time.sleep(.03)
  record('starts_in_clean_single_file_directory',listening)
  record('platform_positional_port',listening and process.poll() is None)
  def req(data,method='POST',path='/',ctype='application/json'):
   body=json.dumps(data,ensure_ascii=False).encode() if not isinstance(data,bytes) else data
   c=http.client.HTTPConnection('127.0.0.1',port,timeout=10);c.request(method,path,body,{'Content-Type':ctype});r=c.getresponse();status=r.status;out=json.loads(r.read());c.close();return status,out
  data=json.loads((W/'tests/tests_v34/fixtures/states.json').read_text(encoding='utf-8'))['game43']['0']['request']
  status,out=req(data);record('real_initial_HTTP_has_actions',status==200 and bool(out['roleCommandMap']) and set(out)=={'roleCommandMap','prompt','executeCmd'})
  record('duplicate_HTTP_idempotent',req(data)==(status,out))
  bad=dict(data);bad['teamOur']=dict(data['teamOur'],goldNum=76)
  record('conflicting_same_round_safely_rejected',req(bad)[1]=={'roleCommandMap':{},'prompt':'','executeCmd':''})
  record('malformed_JSON_safe_empty',req(b'{')[1]['roleCommandMap']=={})
  record('wrong_content_type_safe_empty',req(data,ctype='text/plain')[1]['roleCommandMap']=={})
  record('wrong_route_404',req(data,path='/wrong')[0]==404)
  record('GET_rejected_405',req(b'',method='GET')[0]==405)
  later=dict(data);later['roundNo']=2;record('next_turn_after_bad_requests_recovers',bool(req(later)[1]['roleCommandMap']))
  # HTTP chunked input is supported by the actual platform handler.
  body=json.dumps(later).encode();c=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
  c.request('POST','/',iter([body[:40],body[40:]]),{'Content-Type':'application/json'},encode_chunked=True);r=c.getresponse();body_out=json.loads(r.read());c.close()
  record('chunked_HTTP_request',r.status==200 and body_out==req(later)[1])
 finally:
  process.terminate();process.wait(timeout=5);t.join(timeout=2)
 record('no_companion_files_created',[p.name for p in root.iterdir()]==['main3.py'])
 record('encrypted_log_records_emitted',any('ASL1 ' in line for line in lines))
 record('no_plaintext_replay_or_strategy',not any('REPLAY3 ' in line or '[shadow_turn]' in line for line in lines))
 record('no_runtime_log_drop',not any('SECURE_LOG_DROPPED' in line for line in lines))
 report=json.loads(Path(str(source)+'.build.json').read_text())
 record('same_existing_public_key',report['key_id']=='3a87e18fdab265c1832f94234ab71457')
 record('business_AST_preserved',report['business_ast_unchanged_except_sinks'] and report['task_script_string_constants_unchanged'])
 for value in ['0','65536','not-a-port']:
  p=subprocess.run([sys.executable,'-S','-B','main3.py',value],cwd=root,capture_output=True,timeout=5)
  record('bad_port_'+value,p.returncode==2 and b'ASL1 ' in p.stdout)
(W/'runs/v38/secure_platform_validation.json').write_text(json.dumps({'runtime':sys.version,'checks':results,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scope':'Real TCP localhost, exact encrypted submission only; own production private key not accessed; no official container.'},ensure_ascii=False,indent=2))
print('[verify_secure_platform] platform checks:',len(results),'PASS')
