"""Package the ordinary standalone src/main3.py; no legacy module bundling."""
from __future__ import annotations
import ast
import hashlib
import sys
import tarfile
from pathlib import Path


def build_single_file() -> Path:
    root = Path(__file__).resolve().parents[1]
    source = root / 'src' / 'main3.py'
    target = root / 'CoreGeek' / 'main3.py'
    if not source.is_file():
        raise FileNotFoundError(f'entry source missing: {source}')
    raw = source.read_bytes()
    tree = ast.parse(raw.decode('utf-8'), feature_version=(3, 11))
    for node in ast.walk(tree):
        names = ([node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module
                 else [item.name.split('.')[0] for item in node.names] if isinstance(node, ast.Import) else [])
        if isinstance(node, ast.ImportFrom) and node.level:
            raise ValueError('relative package import is not allowed in the platform entry')
        if any(name not in sys.stdlib_module_names for name in names):
            raise ValueError(f'non-standard-library import: {names}')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    output = root / 'CoreGeek.tar.gz'
    with tarfile.open(output, 'w:gz') as archive:
        archive.add(target, arcname='CoreGeek/main3.py')
    with tarfile.open(output, 'r:gz') as archive:
        assert archive.getnames() == ['CoreGeek/main3.py']
        assert archive.extractfile('CoreGeek/main3.py').read() == raw
    print(f'[build_single_file] build=v3.8-rear-deadline-insurance; sha256={hashlib.sha256(raw).hexdigest()}', flush=True)
    print(f'[build_single_file] archive={output}; entry=CoreGeek/main3.py; dependencies=stdlib-only', flush=True)
    return output


if __name__ == '__main__':
    try:
        build_single_file()
    except (OSError, ValueError, SyntaxError, AssertionError) as exc:
        print(f'[build_single_file] FAILED: {type(exc).__name__}: {exc}', flush=True)
        raise SystemExit(1)
