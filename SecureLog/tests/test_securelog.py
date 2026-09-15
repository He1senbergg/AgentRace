# -*- coding: utf-8 -*-
"""Executable tests; no production private keys are included in this package."""
import ast
import base64
import concurrent.futures
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import securelog_runtime as rt
import log_tool as tool

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa as crsa
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    CRYPTO = True
except ImportError:
    CRYPTO = False

# A fixture of the two log sinks, NOT the complete user's AgentRace code.
FIXTURE = '''# -*- coding: utf-8 -*-
"""A log-integration fixture, not an actual competition player."""
from __future__ import annotations
import threading
STDOUT_LOCK = threading.RLock()
TASK_SCRIPT = "print('task answer: 42')"
def print_log(function: str, message: str, *args) -> None:
    try:
        text = message % args if args else message
        with STDOUT_LOCK:
            print("[" + function + "] " + text, flush=True)
    except Exception:
        pass

def write_task_trace(data: dict, response: dict, memory=None, session_tag="s", sequence=1):
    import json
    with STDOUT_LOCK:
        print("[write_task_trace] REPLAY3 " + json.dumps(data, ensure_ascii=False), flush=True)

def callback(data):
    result = {"roleCommandMap": {}, "prompt": "", "executeCmd": TASK_SCRIPT}
    print_log("handle", "[shadow_turn] %s", "保留300金币")
    write_task_trace(data, result)
    return result

if __name__ == "__main__":
    callback({"roundNo": 1})
'''


class RFCVectors(unittest.TestCase):
    def test_rfc8439_quarter_round(self):
        s = [0x11111111, 0x01020304, 0x9b8d6f43, 0x01234567]
        rt._sl_quarter(s, 0, 1, 2, 3)
        self.assertEqual(s, [0xea2a92f4, 0xcb1cf8ce, 0x4581472e, 0x5881c4bb])

    def test_rfc8439_block(self):
        actual = rt._sl_block(bytes(range(32)), bytes.fromhex('000000090000004a00000000'), 1)
        expected = bytes.fromhex('''10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e
            d2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e''')
        self.assertEqual(actual, expected)

    def test_rfc8439_poly1305(self):
        key = bytes.fromhex('85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b')
        actual = rt._sl_poly1305(b'Cryptographic Forum Research Group', key)
        self.assertEqual(actual.hex(), 'a8061dc1305136c6c22b8baf0c0127a9')

    def test_rfc8439_aead(self):
        key = bytes(range(0x80, 0xa0))
        nonce = bytes.fromhex('070000004041424344454647')
        aad = bytes.fromhex('50515253c0c1c2c3c4c5c6c7')
        plain = b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it."
        expected = bytes.fromhex('''d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d6
            3dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b3692ddbd7f2d778b8c9803aee328091b58
            fab324e4fad675945585808b4831d7bc3ff4def08e4b7a9de576d26586cec64b6116
            1ae10b594f09e26a7e902ecbd0600691''')
        self.assertEqual(rt._sl_seal(key, nonce, plain, aad), expected)
        self.assertEqual(rt._sl_open(key, nonce, expected, aad), plain)

    def test_padding_and_compression_roundtrip(self):
        for raw in (b'', b'a', b'a' * 100000, os.urandom(1000), '中文\n'.encode()):
            with self.subTest(size=len(raw)):
                self.assertEqual(tool.unpack_plain(rt._sl_pack_plain(raw)), raw)

    def test_decompression_bomb_size_mismatch_rejected(self):
        import zlib
        compressed = zlib.compress(b'x' * 100000)
        body = struct.pack('>BII', 1, 1, len(compressed)) + compressed
        body += b'\x00' * (-len(body) % 256)
        with self.assertRaises(ValueError):
            tool.unpack_plain(body)

    def test_nonzero_padding_rejected(self):
        b = rt._sl_pack_plain(b'a')
        with self.assertRaises(ValueError):
            tool.unpack_plain(b[:-1] + b'\x01')

    def test_bad_public_keys_rejected(self):
        for n, e in ((1, 65537), (True, 65537), (2**3071, 65537), (2**3071+1, 3)):
            with self.subTest(nbits=int(n).bit_length(), e=e):
                with self.assertRaises(ValueError):
                    rt._SLSecureLogger(n, e)

    def test_authenticate_before_plaintext_decryption(self):
        with mock.patch.object(rt, '_sl_chacha', side_effect=AssertionError('must not decrypt')):
            with self.assertRaises(ValueError):
                rt._sl_open(b'x'*32, b'\x00'*12, b'y'*32, b'aad')


@unittest.skipUnless(CRYPTO, 'independent cryptography backend unavailable locally')
class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.dir = Path(cls.temp.name)
        cls.key = crsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.n, cls.e = cls.key.public_key().public_numbers().n, 65537
        cls.private_path = cls.dir/'test_only_private.pem'
        cls.private_path.write_bytes(cls.key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        cls.runtime = (ROOT/'securelog_runtime.py').read_text()

    def reader(self):
        return tool.PrivateReader(self.private_path, 'cryptography')

    def emit(self, *messages):
        lines = []
        logger = rt._SLSecureLogger(self.n, self.e, lines.append)
        for message in messages:
            self.assertTrue(logger.emit_bytes(message))
        return lines, logger

    def packet(self, lines):
        return base64.b64decode(''.join(line.split()[-1] for line in lines))

    def test_differential_aead_120_cases(self):
        rng = random.Random(8439)
        sizes = [0,1,15,16,17,31,32,63,64,65,1024,8192] + [rng.randrange(3000) for _ in range(108)]
        for size in sizes:
            key, nonce = os.urandom(32), os.urandom(12)
            plain, aad = os.urandom(size), os.urandom(rng.randrange(100))
            sealed = rt._sl_seal(key, nonce, plain, aad)
            oracle = ChaCha20Poly1305(key)
            self.assertEqual(sealed, oracle.encrypt(nonce, plain, aad))
            self.assertEqual(rt._sl_open(key, nonce, sealed, aad), plain)
            self.assertEqual(oracle.decrypt(nonce, sealed, aad), plain)

    def test_oaep_runtime_to_independent_library(self):
        for _ in range(10):
            secret = os.urandom(32)
            self.assertEqual(self.reader().unwrap(rt._sl_oaep_wrap(secret, self.n, self.e)), secret)

    def test_oaep_independent_library_to_rfc_decoder(self):
        d = self.key.private_numbers().d
        for _ in range(5):
            secret = os.urandom(32)
            wrapped = self.key.public_key().encrypt(secret, padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=rt._SL_LABEL))
            # Test private math uses a reference private exponent; runtime has no private op.
            actual = tool.oaep_unwrap_with_primitive(wrapped, self.n, self.e,
                                                    lambda c: pow(c, d, self.n))
            self.assertEqual(actual, secret)

    def test_oaep_wrong_label_and_modified_ciphertext(self):
        secret = os.urandom(32)
        wrapped = self.key.public_key().encrypt(secret, padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=b'wrong'))
        d = self.key.private_numbers().d
        with self.assertRaises(ValueError):
            tool.oaep_unwrap_with_primitive(wrapped, self.n, self.e, lambda c: pow(c,d,self.n))
        good = rt._sl_oaep_wrap(secret, self.n, self.e)
        with self.assertRaises(ValueError):
            self.reader().unwrap(good[:-1]+bytes([good[-1]^1]))

    def test_full_unicode_empty_and_large_roundtrip(self):
        messages = [b'', '围墙预算=300\n'.encode(), os.urandom(16384), b'z' * 200000]
        lines, _ = self.emit(*messages)
        records, info = tool.decode_lines(lines, self.reader())
        self.assertEqual(records, messages)
        self.assertEqual(info['decoded_records'], 4)
        self.assertNotIn('围墙', '\n'.join(lines))

    def test_all_records_independently_decodable(self):
        lines, _ = self.emit(b'first', b'second')
        tail = [l for l in lines if l.split()[3] == '2']
        records, info = tool.decode_lines(tail, self.reader())
        self.assertEqual(records, [b'second'])
        self.assertEqual(info['missing_sequence_numbers'], 1)

    def test_fragment_reordering(self):
        messages = [os.urandom(10000), b'last']
        lines, _ = self.emit(*messages)
        random.Random(3).shuffle(lines)
        records, _ = tool.decode_lines(lines, self.reader())
        self.assertEqual(records, messages)

    def test_complete_record_duplicates(self):
        lines, _ = self.emit(b'one', b'two')
        records, info = tool.decode_lines(lines + lines, self.reader())
        self.assertEqual(records, [b'one', b'two'])
        self.assertEqual(info['duplicate_records'], 2)

    def test_missing_fragment_preserves_following_record(self):
        lines, _ = self.emit(os.urandom(10000), b'next')
        lines.pop(1)
        records, info = tool.decode_lines(lines, self.reader())
        self.assertEqual(records, [b'next'])
        self.assertEqual(info['incomplete_records'], 1)
        self.assertEqual(info['missing_sequence_numbers'], 1)

    def test_header_tampering_is_rejected(self):
        lines, _ = self.emit(b'protected')
        packet = bytearray(self.packet(lines))
        packet[21] ^= 1
        with self.assertRaises(ValueError):
            tool.decrypt_packet(bytes(packet), self.reader())

    def test_ciphertext_tampering_is_rejected(self):
        lines, _ = self.emit(b'protected')
        packet = bytearray(self.packet(lines))
        packet[-20] ^= 1
        with self.assertRaises(ValueError):
            tool.decrypt_packet(bytes(packet), self.reader())

    def test_outer_sequence_mismatch_is_rejected(self):
        lines, _ = self.emit(b'protected')
        altered = [l.replace(' 1 1/', ' 2 1/') for l in lines]
        records, info = tool.decode_lines(altered, self.reader())
        self.assertEqual(records, [])
        self.assertEqual(info['invalid_records'], 1)

    def test_wrong_private_key_cannot_decrypt(self):
        lines, _ = self.emit(b'protected')
        other = crsa.generate_private_key(public_exponent=65537, key_size=3072)
        target = self.dir/'wrong.pem'
        target.write_bytes(other.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        records, info = tool.decode_lines(lines, tool.PrivateReader(target,'cryptography'))
        self.assertEqual(records, [])
        self.assertEqual(info['foreign_key_records'], 1)

    def test_encryption_failure_drops_without_plaintext(self):
        lines = []
        logger = rt._SLSecureLogger(self.n, self.e, lines.append)
        with mock.patch.object(rt, '_sl_seal', side_effect=ValueError('secret exception')):
            self.assertFalse(logger.emit_text('budget=SECRET'))
        self.assertEqual(lines, ['[_sl_emit_line] SECURE_LOG_DROPPED'])
        self.assertTrue(logger.emit_text('after failure'))
        self.assertEqual(logger._seq, 2)
        self.assertNotIn('SECRET', ''.join(lines))
        records, info = tool.decode_lines(lines, self.reader())
        self.assertEqual(records, [b'after failure'])
        self.assertEqual(info['missing_sequence_numbers'], 1)

    def test_broken_stdout_does_not_raise(self):
        def broken(line):
            raise BrokenPipeError('never echo this')
        logger = rt._SLSecureLogger(self.n, self.e, broken)
        self.assertFalse(logger.emit_text('SECRET'))
        self.assertIsNone(logger.print('SECRET'))

    def test_thread_sequences_are_unique(self):
        lines = []
        logger = rt._SLSecureLogger(self.n,self.e,lines.append)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertTrue(all(pool.map(logger.emit_bytes, [b'thread']*80)))
        records, info = tool.decode_lines(lines,self.reader())
        self.assertEqual(len(records),80)
        self.assertEqual(info.get('missing_sequence_numbers',0),0)

    def test_restarted_and_reset_session_keys_differ(self):
        lines, logger = self.emit(b'first')
        old = logger._key, logger._sid
        logger._after_fork()
        self.assertTrue(logger.emit_bytes(b'child'))
        self.assertNotEqual((logger._key,logger._sid), old)
        records, info = tool.decode_lines(lines,self.reader())
        self.assertEqual(records,[b'first',b'child'])
        self.assertEqual(info['sessions'],2)

    def test_sequence_exhaustion_rekeys(self):
        lines, logger = self.emit(b'first')
        old_sid = logger._sid
        logger._seq = 2**63-1
        logger.emit_bytes(b'new')
        self.assertNotEqual(old_sid, logger._sid)
        self.assertEqual(logger._seq, 1)

    def test_builder_task_strings_and_business_response_preserved(self):
        built, report = tool.build_source(FIXTURE, self.n, self.e, self.runtime)
        original_namespace, new_namespace = {'__name__':'fixture'}, {'__name__':'fixture'}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(FIXTURE,'<test-fixture>','exec'),original_namespace)
            original = original_namespace['callback']({'roundNo':1})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(compile(built,'<test-built-fixture>','exec'),new_namespace)
            actual = new_namespace['callback']({'roundNo':1})
        self.assertEqual(actual, original)
        self.assertEqual(new_namespace['TASK_SCRIPT'],original_namespace['TASK_SCRIPT'])
        self.assertEqual(new_namespace['__doc__'],original_namespace['__doc__'])
        self.assertTrue(report['business_ast_unchanged_except_sinks'])
        self.assertEqual(report['rewritten_print_calls'], {'print_log':1,'write_task_trace':1})
        restored, _ = tool.decode_lines(output.getvalue().splitlines(), self.reader())
        self.assertIn('[shadow_turn]', b''.join(restored).decode())
        self.assertNotIn('[shadow_turn]', output.getvalue())

    def test_single_file_under_isolated_no_site_packages(self):
        built, _ = tool.build_source(FIXTURE,self.n,self.e,self.runtime)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'main3.py'
            path.write_text(built,encoding='utf-8')
            result = subprocess.run([sys.executable,'-I','-S',str(path)],cwd=d,
                capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual([p.name for p in Path(d).iterdir()],['main3.py'])
            restored,info = tool.decode_lines(result.stdout.splitlines(),self.reader())
            self.assertEqual(info['decoded_records'],2)
            self.assertTrue(restored)

    def test_builder_refuses_unknown_print_alias_and_dynamic_exec(self):
        for extra in ('\nprint("secret")\n','\np = print\n','\nexec("print(1)")\n',
                      '\nimport logging\n', '\nimport sys\nsys.stderr.write("secret")\n'):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    tool.build_source(FIXTURE+extra,self.n,self.e,self.runtime)

    def test_builder_refuses_namespace_and_builtin_shadowing(self):
        for extra in ('\ndef _sl_custom(): pass\n', '\nclass _SLSecureLogger: pass\n',
                      '\ndef helper(print): pass\n', '\nimport os as _sl_os\n'):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    tool.build_source(FIXTURE+extra,self.n,self.e,self.runtime)

    def test_record_limit_drops_and_never_falls_back(self):
        lines=[]
        logger=rt._SLSecureLogger(self.n,self.e,lines.append)
        self.assertFalse(logger.emit_bytes(b'x'*(rt._SL_MAX_RAW+1)))
        self.assertEqual(lines,['[_sl_emit_line] SECURE_LOG_DROPPED'])
        self.assertTrue(logger.emit_bytes(b'next'))
        records,info=tool.decode_lines(lines,self.reader())
        self.assertEqual(records,[b'next'])
        self.assertEqual(info['runtime_drop_markers'],1)

    @unittest.skipUnless(hasattr(os,'fork'), 'fork unavailable on this operating system')
    def test_actual_fork_rotates_key_and_replaces_lock(self):
        lines,logger=self.emit(b'parent')
        old_sid=logger._sid
        readfd,writefd=os.pipe()
        pid=os.fork()
        if pid==0:
            try:
                captured=[]
                logger._sink=captured.append
                ok=logger.emit_bytes(b'child')
                data=json.dumps({'ok':ok,'sid':logger._sid.hex(),'lines':captured}).encode()
                os.write(writefd,data)
                os._exit(0)
            except BaseException:
                os._exit(2)
        os.close(writefd)
        with os.fdopen(readfd,'rb') as inp:
            child=json.loads(inp.read())
        _,status=os.waitpid(pid,0)
        self.assertEqual(status,0)
        self.assertTrue(child['ok'])
        self.assertNotEqual(child['sid'],old_sid.hex())
        records,info=tool.decode_lines(lines+child['lines'],self.reader())
        self.assertEqual(records,[b'parent',b'child'])
        self.assertEqual(info['sessions'],2)

    def test_builder_refuses_old_bundle_missing_top_level_sinks(self):
        with self.assertRaises(ValueError):
            tool.build_source('exec("print(42)")', self.n,self.e,self.runtime)

    def test_builder_unicode_offset(self):
        variant = FIXTURE.replace('print("["', '注释 = "中文"; print("["')
        built,report = tool.build_source(variant,self.n,self.e,self.runtime)
        self.assertTrue(report['business_ast_unchanged_except_sinks'])
        compile(built,'<unicode-fixture>','exec')

    def test_builder_refuses_repeat_insertion(self):
        built,_=tool.build_source(FIXTURE,self.n,self.e,self.runtime)
        with self.assertRaises(ValueError):
            tool.build_source(built,self.n,self.e,self.runtime)

    def test_keygen_selfcheck_exclusive_files_and_build_cli_workflow(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            report=tool.keygen(d/'keys',3072,'cryptography')
            n,e=tool.load_public(d/'keys/public.json')
            self.assertEqual(report['key_id'],rt._sl_key_id(n,e).hex())
            if os.name!='nt':
                self.assertEqual((d/'keys/private.pem').stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):
                tool.keygen(d/'keys',3072,'cryptography')
            source=d/'source.py'
            source.write_text(FIXTURE,encoding='utf-8')
            target=d/'submit/main3.py'
            tool.build(source,d/'keys/public.json',target)
            self.assertEqual(source.read_text(),FIXTURE)
            self.assertNotIn('BEGIN RSA PRIVATE KEY',target.read_text())
            with self.assertRaises(FileExistsError):
                tool.build(source,d/'keys/public.json',target)
            with self.assertRaises(ValueError):
                tool.build(source,d/'keys/public.json',source)
            result=subprocess.run([sys.executable,'-I','-S',str(target)],
                capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            log=d/'game.log'; log.write_text(result.stdout,encoding='utf-8')
            report,status=tool.decrypt_file(d/'keys/private.pem',log,d/'restored.log','cryptography')
            self.assertEqual(status,0)
            self.assertIn('[shadow_turn]',(d/'restored.log').read_text())
            with self.assertRaises(FileExistsError):
                tool.decrypt_file(d/'keys/private.pem',log,d/'restored.log','cryptography')

    def test_decode_limits_and_plaintext_mixed_file_reporting(self):
        lines,_=self.emit(b'a')
        records,info=tool.decode_lines(['[handle] [shadow_turn] secret','x'*8193]+lines,self.reader())
        self.assertEqual(records,[b'a'])
        self.assertEqual(info['plaintext_strategy_markers'],1)
        self.assertEqual(info['oversize_lines'],1)
        self.assertIn('unknown',info['tail_completeness'])

    def test_conflicting_incomplete_fragment_rejected(self):
        lines,_=self.emit(os.urandom(10000))
        first=lines[0]
        replacement=first[:-1]+('A' if first[-1]!='A' else 'B')
        records,info=tool.decode_lines([first,replacement]+lines[1:],self.reader())
        self.assertEqual(records,[])
        self.assertEqual(info['conflicting_fragments'],1)

    def test_rsa4096_roundtrip(self):
        key=crsa.generate_private_key(public_exponent=65537,key_size=4096)
        numbers=key.public_key().public_numbers()
        secret=os.urandom(32)
        wrapped=rt._sl_oaep_wrap(secret,numbers.n,numbers.e)
        actual=key.decrypt(wrapped,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),label=rt._SL_LABEL))
        self.assertEqual(actual,secret)


@unittest.skipUnless(importlib.util.find_spec('rsa'), 'rsa package not available in this test environment')
class ActualRSABackend(unittest.TestCase):
    def test_actual_rsa_keygen_load_blinded_decrypt_and_full_log(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            tool.keygen(d/'keys',3072,'rsa')
            n,e=tool.load_public(d/'keys/public.json')
            lines=[]
            logger=rt._SLSecureLogger(n,e,lines.append)
            self.assertTrue(logger.emit_text('使用真实 rsa 后端'))
            reader=tool.PrivateReader(d/'keys/private.pem','rsa')
            records,info=tool.decode_lines(lines,reader)
            self.assertEqual(records,['使用真实 rsa 后端'.encode()])
            self.assertEqual(info['decoded_records'],1)


if __name__=='__main__':
    unittest.main(verbosity=2)
