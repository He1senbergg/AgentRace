"""Read-only, bounded inspection packets for the opt-in survival task pipeline.

The generated command runs in the COMPETITION sandbox. No game task files,
answers, tokens, URLs or credentials from archived opponents are embedded.
"""
import re
import shlex


def fast_task_discovery_command(text: str) -> str | None:
    """Read the named brief, related public docs and referenced source in one turn.

    `text` is the current phaseTask. Returns one shell command, or None when
    there is no unambiguous Markdown filename. Reading a file is not solving it.
    """
    names = sorted(set(re.findall(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,120}\.md\b", text)))
    if not names:
        return None
    script = 'import os,re,json,time\nNAMES=' + repr(names[:8]) + '\n'
    script += r'''
started=time.monotonic(); visited=0; found=[]; seen=set(); limited=False
roots=['/tmp/selfEvolutionTask', os.getcwd(), '/tmp']
for root in roots:
 if found: break
 for directory, dirs, files in os.walk(root,followlinks=False):
  visited+=1
  dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in ('node_modules','__pycache__'))
  if directory[len(root):].count(os.sep)>=5: dirs[:]=[]
  if visited>1200 or time.monotonic()-started>4:
   limited=True;break
  for name in NAMES:
   p=os.path.join(directory,name)
   if name in files and not os.path.islink(p): found.append(os.path.abspath(p))
  if found: break
packets=[]; available=[]; queued=[]; budget=11000
for taskfile in found[:8]:
 root=os.path.dirname(taskfile)
 try:
  with open(taskfile,encoding='utf-8',errors='replace') as stream: brief=stream.read(8001)
 except OSError: continue
 queued.append(taskfile)
 # Only explicitly mentioned child workspaces: never sweep sibling tasks.
 words=set(re.findall(r'[A-Za-z0-9_.-]+',brief))
 scopes=[root]
 try:
  for name in sorted(os.listdir(root)):
   p=os.path.join(root,name)
   if name in words and os.path.isdir(p) and not os.path.islink(p):scopes.append(p)
 except OSError: pass
 refs=set(re.findall(r'(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:py|sh|md|json|toml|yaml|yml)\b',brief))
 for scope in scopes:
  for name in ['API_DOCS.md','README.md','spec.md']:queued.append(os.path.join(scope,name))
  # Explicit references are resolved only inside the task directory.
  for ref in sorted(refs):
   p=os.path.abspath(os.path.join(scope,ref))
   if os.path.commonpath([root,p])==root:queued.append(p)
  for directory,dirs,files in os.walk(scope,followlinks=False):
   dirs[:]=[] if directory[len(scope):].count(os.sep)>=1 else sorted(d for d in dirs if not d.startswith('.') and d not in ('__pycache__','node_modules'))
   if scope==root:dirs[:]=[]
   for name in sorted(files):
    path=os.path.join(directory,name)
    if len(available)<48:available.append(os.path.relpath(path,root))
    if name.endswith(('.py','.sh')) and not os.path.islink(path):queued.append(path)
allowed_roots={os.path.realpath(os.path.dirname(p)) for p in found}
for path in queued:
 if not any(os.path.commonpath([root,os.path.realpath(path)])==root for root in allowed_roots):continue
 if path in seen or not os.path.isfile(path) or os.path.islink(path):continue
 seen.add(path)
 if len(packets)>=16 or budget<=0:
  limited=True;break
 try:
  with open(path,encoding='utf-8',errors='replace') as stream: content=stream.read(min(budget,6000)+1)
  cap=min(budget,6000);cut=len(content)>cap
  packets.append(dict(path=path,text=content[:cap],truncated=cut));budget-=min(len(content),cap)
 except OSError as exc:packets.append(dict(path=path,error=type(exc).__name__))
packet=dict(documents=packets,available_files=sorted(set(available)),search_limited=limited,
            output_limited=any(d.get('truncated',False) for d in packets),inspection_only=True)
while len(json.dumps(packet,ensure_ascii=False))>14000:
 packet['output_limited']=True
 largest=max(packets,key=lambda d:len(d.get('text','')),default=None)
 if largest is None or not largest.get('text'):
  if packet['available_files']:packet['available_files'].pop();continue
  if packets:packets.pop();continue
  break
 largest['text']=largest['text'][:len(largest['text'])//2];largest['truncated']=True
print(json.dumps(packet,ensure_ascii=False))
'''
    return 'python3 -c ' + shlex.quote(script)


TASK_FAST_GUIDANCE = (
    'TURN-EFFICIENT EXECUTION: the inspection packet includes the current brief, related docs and referenced source. '
    'Do not reread complete files already present. Prefer one compound Python command for the required dependent '
    'localhost API calls, or one patch-plus-documented-check command. Budget request/subprocess timeouts within '
    'the 15-second command limit. For repairs, change only the permitted implementation, never the checker, '
    'tests, specification or grading data. Capture checker output rather than mixing it with the answer. '
    'Assert that the documented check succeeded before using its output. Only when the brief explicitly asks '
    'for a checker-produced token, extract that CURRENT token and encode it in the REQUIRED answer schema. '
    'For APIs, implement documented authentication, pagination, transformations, field names and units together; '
    'validate responses instead of guessing missing values. Print ONLY the final required taskAnswer to stdout '
    'and set answer_from_stdout=true on that command; put diagnostics on stderr. On incomplete checks or failed '
    'requests, exit nonzero and leave automatic submission disabled. This can eliminate the extra LLM turn '
    'between a successful computation and submission. The task is not considered solved merely because a '
    'command exited successfully. Never reuse any token/answer from another task. '
)
