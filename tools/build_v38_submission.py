"""Build encrypted-log single-file submission using the user's EXISTING public key."""
from __future__ import annotations
import argparse,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'SecureLog'))
from log_tool import build

def build_v38_submission(public: Path) -> Path:
    if not public.is_file():
        raise FileNotFoundError(f'公钥文件不存在：{public}；沿用已有公钥，不要重新生成密钥。')
    entry=ROOT/'AgentRace_Submission/main3.py'
    report=build(ROOT/'src/main3.py',public,entry,force=True)
    archive=entry.parent/'CoreGeek.tar.gz'
    with tarfile.open(archive,'w:gz') as target:target.add(entry,arcname='CoreGeek/main3.py')
    with tarfile.open(archive,'r:gz') as target:
        assert target.getnames()==['CoreGeek/main3.py']
        assert target.extractfile('CoreGeek/main3.py').read()==entry.read_bytes()
    print('[build_v38_submission] '+json.dumps(dict(archive=str(archive),**report),ensure_ascii=False),flush=True)
    return archive

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public',type=Path,default=ROOT/'AgentRace_LogKeys/public.json')
    args=parser.parse_args()
    try:build_v38_submission(args.public)
    except (OSError,ValueError,AssertionError) as exc:
        print(f'[build_v38_submission] 失败：{exc}',flush=True);raise SystemExit(1)
