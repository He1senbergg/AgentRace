# -*- coding: utf-8 -*-
"""LOCAL ONLY: key generation, conservative single-file build, log decryption.

The platform must receive ONLY the build output, never this tool or private.pem.
Local key backend: existing rsa==4.9 preferred; cryptography is an optional local
alternative used for independent interoperability validation. Neither is required
by the generated platform runtime.
"""
import argparse
import ast
import base64
import collections
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import struct
import sys
import zlib

import securelog_runtime as rt

BASE = Path(__file__).resolve().parent
MAX_PACKET = rt._SL_MAX_BODY + 2048
MAX_PENDING_BYTES = 8 * 1024 * 1024
MAX_PLAIN_BYTES = 256 * 1024 * 1024
MARKER = '# BEGIN AGENTRACE_SECURELOG_ASL1'


def write_new(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Exclusive creation: never overwrite a key/source/log silently."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
    except Exception:
        # An incomplete new output is never advertised as complete.
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _backend(name: str) -> str:
    if name in ('auto', 'rsa'):
        try:
            import rsa
            return 'rsa'
        except ImportError:
            if name == 'rsa':
                raise RuntimeError('本地没有 rsa；这不是要求给比赛平台安装包') from None
    if name in ('auto', 'cryptography'):
        try:
            import cryptography
            return 'cryptography'
        except ImportError:
            pass
    raise RuntimeError('本地密钥工具需要现有 rsa，或本地已有的 cryptography')


def _public_document(n: int, e: int) -> dict:
    return {'format': 'agentrace-rsa-public-v1', 'n_hex': format(n, 'x'),
            'e': e, 'key_id': rt._sl_key_id(n, e).hex()}


def load_public(path: Path):
    data = path.expanduser().read_bytes()
    if len(data) > 4096 or b'PRIVATE KEY' in data:
        raise ValueError('需要 public.json；禁止把私钥传入构建器')
    obj = json.loads(data)
    if not isinstance(obj, dict) or set(obj) != {'format', 'n_hex', 'e', 'key_id'}:
        raise ValueError('invalid public.json structure')
    if obj['format'] != 'agentrace-rsa-public-v1' or not isinstance(obj['n_hex'], str):
        raise ValueError('invalid public.json format')
    n, e = int(obj['n_hex'], 16), obj['e']
    rt._sl_validate_public(n, e)
    if obj['key_id'] != rt._sl_key_id(n, e).hex():
        raise ValueError('public key fingerprint mismatch')
    return n, e


def oaep_unwrap_with_primitive(wrapped: bytes, n: int, e: int, private_op) -> bytes:
    """RFC 8017 7.1.2, restricted to our 32-byte session key.

    private_op is rsa.PrivateKey.blinded_decrypt in the rsa backend.
    One generic error. This offline function has NO constant-time guarantee.
    """
    k = (n.bit_length() + 7) // 8
    if len(wrapped) != k or int.from_bytes(wrapped, 'big') >= n:
        raise ValueError('key unwrap failed')
    ci = int.from_bytes(wrapped, 'big')
    em_int = private_op(ci)
    em = em_int.to_bytes(k, 'big')
    masked_seed, masked_db = em[1:33], em[33:]
    seed = rt._sl_xor(masked_seed, rt._sl_mgf1(masked_db, 32))
    db = rt._sl_xor(masked_db, rt._sl_mgf1(seed, k - 33))
    expected_prefix = hashlib.sha256(rt._SL_LABEL).digest() + b'\x00' * (k - 98) + b'\x01'
    valid = (em[0] == 0) & hmac.compare_digest(db[:-32], expected_prefix)
    valid &= (pow(em_int, e, n) == ci)
    if not valid:
        raise ValueError('key unwrap failed')
    return db[-32:]


class PrivateReader:
    """Loads a private key on the local machine only. Never print its contents."""
    def __init__(self, path: Path, backend='auto'):
        self.backend = _backend(backend)
        raw = path.expanduser().read_bytes()
        if len(raw) > 16384:
            raise ValueError('invalid private key file')
        if self.backend == 'rsa':
            import rsa
            self.key = rsa.PrivateKey.load_pkcs1(raw, format='PEM')
            self.n, self.e = self.key.n, self.key.e
        else:
            from cryptography.hazmat.primitives import serialization
            self.key = serialization.load_pem_private_key(raw, password=None)
            nums = self.key.public_key().public_numbers()
            self.n, self.e = nums.n, nums.e
        rt._sl_validate_public(self.n, self.e)
        self.kid = rt._sl_key_id(self.n, self.e)
        self.cache = collections.OrderedDict()

    def unwrap(self, wrapped: bytes) -> bytes:
        if self.backend == 'rsa':
            return oaep_unwrap_with_primitive(wrapped, self.n, self.e,
                                              self.key.blinded_decrypt)
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        key = self.key.decrypt(wrapped, padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(),
            label=rt._SL_LABEL))
        if len(key) != 32:
            raise ValueError('key unwrap failed')
        return key


class ForeignKey(ValueError):
    pass


def unpack_plain(body: bytes) -> bytes:
    if not 9 <= len(body) <= rt._SL_MAX_BODY or len(body) % 256:
        raise ValueError('invalid record body')
    codec, raw_len, stored_len = struct.unpack('>BII', body[:9])
    if codec not in (0, 1) or raw_len > rt._SL_MAX_RAW or stored_len > len(body) - 9:
        raise ValueError('invalid record lengths')
    # Only the encoder's minimal 256-byte zero-padding is accepted.
    if len(body) != ((9 + stored_len + 255) // 256) * 256:
        raise ValueError('invalid padding length')
    if any(body[9 + stored_len:]):
        raise ValueError('invalid padding')
    content = body[9:9 + stored_len]
    if codec == 0:
        raw = content
    else:
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(content, raw_len + 1)
        if (not decompressor.eof or decompressor.unused_data or
                decompressor.unconsumed_tail):
            raise ValueError('invalid compressed body')
    if len(raw) != raw_len:
        raise ValueError('raw size mismatch')
    return raw


def decrypt_packet(packet: bytes, reader: PrivateReader):
    if not 54 <= len(packet) <= MAX_PACKET or packet[:4] != rt._SL_MAGIC:
        raise ValueError('invalid encrypted packet')
    kid, sid = packet[4:20], packet[20:36]
    if not hmac.compare_digest(kid, reader.kid):
        raise ForeignKey('different key id')
    seq = int.from_bytes(packet[36:44], 'big')
    wrapped_len = int.from_bytes(packet[44:46], 'big')
    if not 1 <= seq < 2**63 or wrapped_len != (reader.n.bit_length() + 7) // 8:
        raise ValueError('invalid packet header')
    header_len = 50 + wrapped_len
    if len(packet) < header_len + 16:
        raise ValueError('truncated encrypted packet')
    wrapped = packet[46:46 + wrapped_len]
    sealed_len = int.from_bytes(packet[46 + wrapped_len:header_len], 'big')
    if sealed_len != len(packet) - header_len:
        raise ValueError('sealed size mismatch')
    identity = (sid, wrapped)
    key = reader.cache.get(identity)
    if key is None:
        key = reader.unwrap(wrapped)
    body = rt._sl_open(key, seq.to_bytes(12, 'big'), packet[header_len:], packet[:header_len])
    raw = unpack_plain(body)
    # Cache only after a valid AEAD record; bound memory for mixed sessions.
    reader.cache[identity] = key
    reader.cache.move_to_end(identity)
    while len(reader.cache) > 32:
        reader.cache.popitem(last=False)
    return sid.hex(), seq, raw


def keygen(out: Path, bits: int, backend: str) -> dict:
    backend = _backend(backend)
    out = out.expanduser()
    if out.exists():
        raise FileExistsError('密钥目录已存在；拒绝覆盖。更换目录或使用原公钥')
    if backend == 'rsa':
        import rsa
        pub, priv = rsa.newkeys(bits, exponent=65537)
        n, e = pub.n, pub.e
        private_pem, public_pem = priv.save_pkcs1('PEM'), pub.save_pkcs1('PEM')
    else:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa as c_rsa
        priv = c_rsa.generate_private_key(public_exponent=65537, key_size=bits)
        nums = priv.public_key().public_numbers()
        n, e = nums.n, nums.e
        private_pem = priv.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
        public_pem = priv.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.PKCS1)
    doc = _public_document(n, e)
    out.mkdir(parents=True, mode=0o700)
    try:
        write_new(out / 'private.pem', private_pem)
        write_new(out / 'public.pem', public_pem, 0o644)
        write_new(out / 'public.json', (json.dumps(doc, indent=2) + '\n').encode(), 0o644)
        # End-to-end self-check with the selected backend BEFORE claiming success.
        reader = PrivateReader(out / 'private.pem', backend)
        probe = os.urandom(32)
        if reader.unwrap(rt._sl_oaep_wrap(probe, n, e)) != probe:
            raise ValueError('new key self-check failed')
        check_lines = []
        logger = rt._SLSecureLogger(n, e, check_lines.append)
        sample = '[keygen] 日志加解密自检\n'.encode('utf-8')
        if not logger.emit_bytes(sample):
            raise ValueError('new key log encryption self-check failed')
        decoded, check_report = decode_lines(check_lines, reader)
        if decoded != [sample] or check_report.get('invalid_records', 0):
            raise ValueError('new key log decryption self-check failed')
    except Exception:
        # Keep private material for diagnosis/recovery; never print it.
        raise RuntimeError('密钥自检或保存失败；不要上传该目录内任何文件') from None
    return {'key_id': doc['key_id'], 'bits': bits, 'local_backend': backend,
            'private_file': str(out / 'private.pem'), 'public_file': str(out / 'public.json'),
            'oaep_and_log_roundtrip_selfcheck': True}


class _SinkVisitor(ast.NodeVisitor):
    """Conservative static audit, NOT a proof against every dynamic output path."""
    def __init__(self):
        self.stack = []
        self.calls = []
        self.unknown = []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        owner = self.stack[0] if self.stack else '<module>'
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            if owner in ('print_log', 'write_task_trace'):
                if any(k.arg not in ('flush', 'sep', 'end') for k in node.keywords):
                    self.unknown.append((node.lineno, 'unreviewed print arguments'))
                self.calls.append((owner, node.func))
            else:
                self.unknown.append((node.lineno, 'print outside audited functions'))
        elif isinstance(node.func, ast.Name) and node.func.id in ('exec', 'eval', 'compile'):
            self.unknown.append((node.lineno, 'dynamic executable code requires review'))
        elif isinstance(node.func, ast.Attribute):
            name = ast.unparse(node.func)
            if (name.endswith(('.stdout.write', '.stderr.write', '.stdout.writelines',
                               '.stderr.writelines', '.stdout.buffer.write',
                               '.stderr.buffer.write')) or
                    name in ('builtins.print', 'os.write', 'traceback.print_exc',
                             'traceback.print_exception', 'logging.basicConfig')):
                self.unknown.append((node.lineno, 'unreviewed output sink'))
        self.generic_visit(node)


def build_source(source: str, n: int, e: int, runtime_source: str):
    if MARKER in source or re.search(r'-----BEGIN [A-Z ]*PRIVATE KEY-----', source):
        raise ValueError('already built or private key found in source')
    tree = ast.parse(source, feature_version=(3, 11))
    defs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not {'print_log', 'write_task_trace'} <= defs.keys():
        raise ValueError('仅支持包含顶层 print_log/write_task_trace 的普通单文件；未修改源文件')
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else
                node.arg if isinstance(node, ast.arg) else
                (node.asname or node.name.split('.')[0]) if isinstance(node, ast.alias) else '')
        if name.startswith(('_sl_', '_SL')):
            raise ValueError('securelog namespace collision')
        if name == 'print' and not isinstance(node, ast.Name):
            raise ValueError('shadowing builtin print requires manual review')
    visitor = _SinkVisitor()
    visitor.visit(tree)
    # Reject print aliases, shadowing, and non-call uses rather than silently miss them.
    called_ids = {id(func) for _, func in visitor.calls}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == 'print' and id(node) not in called_ids:
            visitor.unknown.append((node.lineno, 'unreviewed print reference/alias'))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
            if any(m.split('.')[0] in ('logging', 'loguru') for m in modules):
                visitor.unknown.append((node.lineno, 'logging framework requires review'))
    counts = collections.Counter(name for name, _ in visitor.calls)
    if visitor.unknown or set(counts) != {'print_log', 'write_task_trace'}:
        raise ValueError('日志出口需人工复核，拒绝构建：' + json.dumps(visitor.unknown[:20], ensure_ascii=False))
    data = source.encode('utf-8')
    lines = data.splitlines(keepends=True)
    starts, cursor = [], 0
    for line in lines:
        starts.append(cursor)
        cursor += len(line)
    edits = []
    for _, func in visitor.calls:
        start = starts[func.lineno - 1] + func.col_offset
        end = starts[func.end_lineno - 1] + func.end_col_offset
        if data[start:end] != b'print':
            raise ValueError('source position mismatch')
        edits.append((start, end, b'_sl_secure_print'))
    modified = data
    for start, end, replacement in sorted(edits, reverse=True):
        modified = modified[:start] + replacement + modified[end:]
    restored_ast = ast.parse(modified.decode('utf-8'))
    for node in ast.walk(restored_ast):
        if isinstance(node, ast.Name) and node.id == '_sl_secure_print':
            node.id = 'print'
    if ast.dump(tree, include_attributes=False) != ast.dump(restored_ast, include_attributes=False):
        raise ValueError('unexpected business AST change')
    # Preserve module docstring and future imports before the inserted runtime.
    preamble_end = 0
    for index, node in enumerate(tree.body):
        if index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            preamble_end = node.end_lineno
        elif isinstance(node, ast.ImportFrom) and node.module == '__future__':
            preamble_end = node.end_lineno
        else:
            break
    if preamble_end == 0:
        # Keep shebang/coding/comment preamble before the first statement.
        preamble_end = tree.body[0].lineno - 1
    modified_lines = modified.decode('utf-8').splitlines(keepends=True)
    initialization = ('\n' + MARKER + '\n' + runtime_source + '\n' +
        '# Only RSA PUBLIC numbers are embedded below. No companion files.\n' +
        f'_sl_sink = _SLSecureLogger(n={n}, e={e})\n' +
        '_sl_secure_print = _sl_sink.print\n' +
        '# END AGENTRACE_SECURELOG_ASL1\n\n')
    output = ''.join(modified_lines[:preamble_end]) + initialization + ''.join(modified_lines[preamble_end:])
    ast.parse(output, feature_version=(3, 11))
    compile(output, '<single-file-build>', 'exec')
    report = {'format': 'agentrace-build-report-v1', 'key_id': rt._sl_key_id(n, e).hex(),
              'source_sha256': hashlib.sha256(data).hexdigest(),
              'output_sha256': hashlib.sha256(output.encode()).hexdigest(),
              'rewritten_print_calls': dict(counts), 'business_ast_unchanged_except_sinks': True,
              'task_script_string_constants_unchanged': True,
              'runtime_third_party_imports': [], 'official_platform_tested': False,
              'static_audit_is_not_complete_dynamic_leak_proof': True}
    return output, report


def build(source_path: Path, public_path: Path, output_path: Path) -> dict:
    source_path, output_path = source_path.expanduser(), output_path.expanduser()
    if source_path.resolve() == output_path.resolve():
        raise ValueError('输出必须使用新路径，不能覆盖源代码')
    n, e = load_public(public_path)
    source = source_path.read_text(encoding='utf-8-sig')
    output, report = build_source(source, n, e, (BASE / 'securelog_runtime.py').read_text(encoding='utf-8'))
    report_path = Path(str(output_path) + '.build.json')
    if output_path.exists() or report_path.exists():
        raise FileExistsError('输出或构建报告已存在，拒绝覆盖')
    write_new(output_path, output.encode(), 0o644)
    write_new(report_path, (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    return report


_LINE = re.compile(r'^([0-9a-f]{32}) ([1-9][0-9]{0,18}) ([1-9][0-9]{0,3})/([1-9][0-9]{0,3}) ([A-Za-z0-9+/=]+)$')


def decode_lines(lines, reader: PrivateReader):
    pending = collections.OrderedDict()
    records = {}
    order = {}
    poisoned = set()
    pending_bytes = plain_bytes = 0
    report = collections.Counter()
    for line in lines:
        report['input_lines'] += 1
        if len(poisoned) > 100000:
            raise ValueError('too many invalid records')
        if len(line) > 8192:
            report['oversize_lines'] += 1
            continue
        if 'SECURE_LOG_DROPPED' in line:
            report['runtime_drop_markers'] += 1
        pos = line.find(rt._SL_PREFIX)
        if pos < 0:
            report['ignored_lines'] += 1
            if 'REPLAY3 ' in line or '[shadow_turn]' in line:
                report['plaintext_strategy_markers'] += 1
            continue
        match = _LINE.fullmatch(line[pos + len(rt._SL_PREFIX):].rstrip('\r\n'))
        if not match:
            report['malformed_lines'] += 1
            continue
        sid, seq, part, parts, chunk = match.groups()
        seq, part, parts = int(seq), int(part), int(parts)
        if not (1 <= seq < 2**63 and 1 <= part <= parts <= 512 and len(chunk) <= rt._SL_CHUNK):
            report['malformed_lines'] += 1
            continue
        key = sid, seq
        if key in poisoned:
            continue
        if key not in pending:
            pending[key] = {'parts': parts, 'chunks': {}}
        item = pending[key]
        if item['parts'] != parts or (part in item['chunks'] and item['chunks'][part] != chunk):
            report['conflicting_fragments'] += 1
            pending_bytes -= sum(map(len, item['chunks'].values()))
            del pending[key]
            poisoned.add(key)
            if len(poisoned) > 100000:
                raise ValueError('too many invalid records')
            if key in records:
                plain_bytes -= len(records[key][1])
                del records[key]
            continue
        if part not in item['chunks']:
            item['chunks'][part] = chunk
            pending_bytes += len(chunk)
        else:
            report['duplicate_fragments'] += 1
        if len(item['chunks']) == parts:
            encoded = ''.join(item['chunks'][i] for i in range(1, parts + 1))
            pending_bytes -= len(encoded)
            del pending[key]
            try:
                if len(encoded) > (MAX_PACKET + 2) // 3 * 4:
                    raise ValueError('packet too large')
                packet = base64.b64decode(encoded, validate=True)
                decoded_sid, decoded_seq, raw = decrypt_packet(packet, reader)
                if (decoded_sid, decoded_seq) != key:
                    raise ValueError('outer/inner identity mismatch')
                digest = hashlib.sha256(packet).digest()
                if key in records:
                    if records[key][0] != digest:
                        plain_bytes -= len(records[key][1])
                        del records[key]
                        poisoned.add(key)
                        report['conflicting_records'] += 1
                    else:
                        report['duplicate_records'] += 1
                    continue
                if sid not in order:
                    if len(order) >= 256:
                        raise ValueError('too many sessions')
                    order[sid] = len(order)
                plain_bytes += len(raw)
                if plain_bytes > MAX_PLAIN_BYTES or len(records) >= 100000:
                    raise MemoryError('local restore size limit')
                records[key] = digest, raw
            except ForeignKey:
                report['foreign_key_records'] += 1
            except MemoryError:
                raise
            except Exception:
                report['invalid_records'] += 1
                poisoned.add(key)
        while len(pending) > 256 or pending_bytes > MAX_PENDING_BYTES:
            _, evicted = pending.popitem(last=False)
            pending_bytes -= sum(map(len, evicted['chunks'].values()))
            report['evicted_incomplete_records'] += 1
    report['incomplete_records'] = len(pending)
    report['decoded_records'] = len(records)
    report['sessions'] = len(order)
    report['restored_bytes'] = plain_bytes
    gaps = []
    sorted_keys = sorted(records, key=lambda k: (order[k[0]], k[1]))
    previous = {}
    for sid, seq in sorted_keys:
        prev = previous.get(sid, 0)
        if seq > prev + 1:
            report['missing_sequence_numbers'] += seq - prev - 1
            if len(gaps) < 100:
                gaps.append({'session': sid, 'first': prev + 1, 'last': seq - 1})
        previous[sid] = seq
    info = dict(report)
    info['gap_ranges_first_100'] = gaps
    info['tail_completeness'] = 'unknown: no trusted final record count'
    info['sender_authenticity'] = 'not proven: public-key encryption is not a signature'
    return [records[key][1] for key in sorted_keys], info


def _bounded_lines(stream):
    while True:
        line = stream.readline(8193)
        if not line:
            return
        if len(line) > 8192:
            while line and not line.endswith('\n'):
                line = stream.readline(8193)
            yield 'x' * 8193
        else:
            yield line


def decrypt_file(private_path: Path, input_path: Path, output_path: Path, backend: str):
    output_path = output_path.expanduser()
    report_path = Path(str(output_path) + '.report.json')
    if output_path.exists() or report_path.exists():
        raise FileExistsError('明文输出或报告已存在，拒绝覆盖')
    reader = PrivateReader(private_path, backend)
    with input_path.expanduser().open('r', encoding='utf-8-sig', errors='replace') as source:
        records, report = decode_lines(_bounded_lines(source), reader)
    report['local_backend'] = reader.backend
    write_new(output_path, b''.join(records))
    write_new(report_path, (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    errors = ('incomplete_records', 'evicted_incomplete_records', 'invalid_records',
              'malformed_lines', 'oversize_lines', 'conflicting_fragments',
              'conflicting_records', 'missing_sequence_numbers', 'runtime_drop_markers',
              'plaintext_strategy_markers')
    partial = not report['decoded_records'] or any(report.get(k, 0) for k in errors)
    return report, 2 if partial else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AgentRace 本地密钥/构建/解密工具；不要上传到比赛平台')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('keygen', help='本地生成密钥；默认优先使用 rsa')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--bits', type=int, choices=(3072, 4096), default=3072)
    p.add_argument('--backend', choices=('auto', 'rsa', 'cryptography'), default='auto')
    p = sub.add_parser('build', help='合入公钥和日志组件，生成新的普通单文件')
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--public', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('decrypt', help='在本地把下载日志还原为原诊断文本')
    p.add_argument('--private', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--backend', choices=('auto', 'rsa', 'cryptography'), default='auto')
    args = parser.parse_args(argv)
    try:
        if args.command == 'keygen':
            report = keygen(args.out, args.bits, args.backend)
            print('[keygen] ' + json.dumps(report, ensure_ascii=False), flush=True)
            print('[keygen] private.pem 未做口令加密；保存在受控目录，禁止上传平台/Git/聊天。', flush=True)
            if os.name == 'nt':
                print('[keygen] Windows 的文件模式不等同于 ACL；需自行限制目录访问权限。', flush=True)
            return 0
        if args.command == 'build':
            report = build(args.source, args.public, args.out)
            print('[build] ' + json.dumps(report, ensure_ascii=False), flush=True)
            return 0
        report, status = decrypt_file(args.private, args.input, args.out, args.backend)
        print('[decrypt_file] ' + json.dumps(report, ensure_ascii=False), flush=True)
        return status
    except Exception as exc:
        # Never print key data, ciphertext plaintext, or an arbitrary crypto error.
        if args.command == 'decrypt':
            print('[main] 解密失败：请检查路径、输出是否已存在、私钥格式和本地依赖。', file=sys.stderr, flush=True)
        else:
            print('[main] ' + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
