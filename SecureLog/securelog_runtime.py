# -*- coding: utf-8 -*-
"""AgentRace SecureLog ASL1: self-contained, public-key-only runtime (Python 3.11+).

No third-party imports, disk access, network calls, private keys or exec/eval.
RSAES-OAEP(SHA-256/MGF1-SHA-256), RFC 8017, wraps a random 32-byte key.
ChaCha20-Poly1305, RFC 8439, encrypts each independent log record.

The compact primitives below are an implementation of the RFC algorithms, NOT
an independently audited cryptographic library. They have no constant-time or
secure-memory-erasure guarantee in Python. Only offline local decryption is
provided separately. Do not use this as a general network decryption service.
"""
import base64 as _sl_b64
import builtins as _sl_builtins
import hashlib as _sl_hashlib
import hmac as _sl_hmac
import os as _sl_os
import struct as _sl_struct
import threading as _sl_threading
import zlib as _sl_zlib

_SL_MAGIC = b'ASL1'
_SL_LABEL = b'AgentRace/ASL1/RSA-OAEP-SHA256'
_SL_MAX_RAW = 2 * 1024 * 1024
_SL_MAX_BODY = 256 * 1024
_SL_CHUNK = 1400
_SL_PREFIX = '[_sl_emit_line] ASL1 '


def _sl_xor(a: bytes, b: bytes) -> bytes:
    if len(a) != len(b):
        raise ValueError('length mismatch')
    return bytes(x ^ y for x, y in zip(a, b))


def _sl_mgf1(seed: bytes, size: int) -> bytes:
    """RFC 8017 B.2.1, fixed SHA-256; only short OAEP masks are allowed."""
    if not 0 <= size <= 4096:
        raise ValueError('invalid mask size')
    return b''.join(_sl_hashlib.sha256(seed + i.to_bytes(4, 'big')).digest()
                    for i in range((size + 31) // 32))[:size]


def _sl_validate_public(n: int, e: int) -> None:
    if type(n) is not int or type(e) is not int:
        raise ValueError('invalid public key')
    if n.bit_length() not in (3072, 4096) or n % 2 != 1 or e != 65537:
        raise ValueError('require RSA-3072/4096 with e=65537')


def _sl_key_id(n: int, e: int) -> bytes:
    _sl_validate_public(n, e)
    return _sl_hashlib.sha256(b'ASL1/public-key\x00' +
                             n.to_bytes((n.bit_length() + 7) // 8, 'big') +
                             e.to_bytes(4, 'big')).digest()[:16]


def _sl_oaep_wrap(message: bytes, n: int, e: int) -> bytes:
    """RFC 8017 7.1.1. This is NOT rsa.encrypt()/PKCS#1 v1.5."""
    _sl_validate_public(n, e)
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 66:
        raise ValueError('OAEP message too long')
    db = (_sl_hashlib.sha256(_SL_LABEL).digest() +
          b'\x00' * (k - len(message) - 66) + b'\x01' + message)
    seed = _sl_os.urandom(32)
    masked_db = _sl_xor(db, _sl_mgf1(seed, k - 33))
    masked_seed = _sl_xor(seed, _sl_mgf1(masked_db, 32))
    encoded = b'\x00' + masked_seed + masked_db
    return pow(int.from_bytes(encoded, 'big'), e, n).to_bytes(k, 'big')


def _sl_rotl(x: int, shift: int) -> int:
    return ((x << shift) | (x >> (32 - shift))) & 0xffffffff


def _sl_quarter(s: list, a: int, b: int, c: int, d: int) -> None:
    """RFC 8439 2.1: four add-xor-rotate pairs, modulo 2**32."""
    s[a] = (s[a] + s[b]) & 0xffffffff
    s[d] = _sl_rotl(s[d] ^ s[a], 16)
    s[c] = (s[c] + s[d]) & 0xffffffff
    s[b] = _sl_rotl(s[b] ^ s[c], 12)
    s[a] = (s[a] + s[b]) & 0xffffffff
    s[d] = _sl_rotl(s[d] ^ s[a], 8)
    s[c] = (s[c] + s[d]) & 0xffffffff
    s[b] = _sl_rotl(s[b] ^ s[c], 7)


def _sl_block(key: bytes, nonce: bytes, counter: int) -> bytes:
    """RFC 8439 2.3: 20 rounds; IETF 96-bit nonce / 32-bit block counter."""
    if len(key) != 32 or len(nonce) != 12 or not 0 <= counter < 2**32:
        raise ValueError('invalid ChaCha parameters')
    initial = list(_sl_struct.unpack('<4I', b'expand 32-byte k'))
    initial += list(_sl_struct.unpack('<8I', key)) + [counter]
    initial += list(_sl_struct.unpack('<3I', nonce))
    state = initial.copy()
    for _ in range(10):
        for args in ((0, 4, 8, 12), (1, 5, 9, 13), (2, 6, 10, 14),
                     (3, 7, 11, 15), (0, 5, 10, 15), (1, 6, 11, 12),
                     (2, 7, 8, 13), (3, 4, 9, 14)):
            _sl_quarter(state, *args)
    return _sl_struct.pack('<16I', *[(a + b) & 0xffffffff
                                    for a, b in zip(initial, state)])


def _sl_chacha(key: bytes, nonce: bytes, message: bytes) -> bytes:
    if len(message) > _SL_MAX_RAW + 4096:
        raise ValueError('cipher input too large')
    out = bytearray(len(message))
    for offset in range(0, len(message), 64):
        block = message[offset:offset + 64]
        stream = _sl_block(key, nonce, 1 + offset // 64)
        out[offset:offset + len(block)] = _sl_xor(block, stream[:len(block)])
    return bytes(out)


def _sl_poly1305(message: bytes, one_time_key: bytes) -> bytes:
    """RFC 8439 2.5; caller MUST derive a different key for each nonce."""
    if len(one_time_key) != 32:
        raise ValueError('invalid Poly1305 key')
    r = int.from_bytes(one_time_key[:16], 'little') & 0x0ffffffc0ffffffc0ffffffc0fffffff
    s = int.from_bytes(one_time_key[16:], 'little')
    acc = 0
    for offset in range(0, len(message), 16):
        term = int.from_bytes(message[offset:offset + 16] + b'\x01', 'little')
        acc = ((acc + term) * r) % (2**130 - 5)
    return ((acc + s) % 2**128).to_bytes(16, 'little')


def _sl_mac_input(aad: bytes, ciphertext: bytes) -> bytes:
    return (aad + b'\x00' * (-len(aad) % 16) +
            ciphertext + b'\x00' * (-len(ciphertext) % 16) +
            _sl_struct.pack('<QQ', len(aad), len(ciphertext)))


def _sl_seal(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    ciphertext = _sl_chacha(key, nonce, plaintext)
    otk = _sl_block(key, nonce, 0)[:32]
    return ciphertext + _sl_poly1305(_sl_mac_input(aad, ciphertext), otk)


def _sl_open(key: bytes, nonce: bytes, sealed: bytes, aad: bytes) -> bytes:
    """Used by the local tool; verify the tag BEFORE decrypting/decompressing."""
    if len(sealed) < 16:
        raise ValueError('authentication failed')
    ciphertext, tag = sealed[:-16], sealed[-16:]
    expected = _sl_poly1305(_sl_mac_input(aad, ciphertext),
                           _sl_block(key, nonce, 0)[:32])
    if not _sl_hmac.compare_digest(tag, expected):
        raise ValueError('authentication failed')
    return _sl_chacha(key, nonce, ciphertext)


def _sl_pack_plain(raw: bytes) -> bytes:
    if len(raw) > _SL_MAX_RAW:
        raise ValueError('record too large')
    compressed = _sl_zlib.compress(raw, level=1)
    use_compressed = len(compressed) < len(raw)
    content = compressed if use_compressed else raw
    # Framing and padding are INSIDE the authenticated ciphertext.
    body = _sl_struct.pack('>BII', int(use_compressed), len(raw), len(content)) + content
    body += b'\x00' * (-len(body) % 256)
    if len(body) > _SL_MAX_BODY:
        raise ValueError('compressed record too large')
    return body


def _sl_emit_line(line: str) -> None:
    """Only ciphertext or fixed, non-sensitive diagnostics reach this sink."""
    _sl_builtins.print(line, flush=True)


class _SLSecureLogger:
    """Independent, thread-safe encryption state; never uses strategy RNG/state.

    n/e: public RSA numbers, NOT a password. New process => new symmetric key.
    sink: accepts one str; default is print(..., flush=True), not a file.
    """
    def __init__(self, n: int, e: int = 65537, sink=None):
        _sl_validate_public(n, e)
        self._n, self._e = n, e
        self._kid = _sl_key_id(n, e)
        self._sink = sink if sink is not None else _sl_emit_line
        self._lock = _sl_threading.RLock()
        self._pid = None
        self._key = None
        self._sid = None
        self._wrapped = None
        self._seq = 0
        self._failures = 0
        if hasattr(_sl_os, 'register_at_fork'):
            _sl_os.register_at_fork(after_in_child=self._after_fork)

    def _after_fork(self):
        # A inherited lock may be locked by a vanished thread; replace it.
        self._lock = _sl_threading.RLock()
        self._pid = None
        self._key = self._sid = self._wrapped = None
        self._seq = 0

    def _new_session(self):
        key = _sl_os.urandom(32)
        sid = _sl_os.urandom(16)
        wrapped = _sl_oaep_wrap(key, self._n, self._e)
        self._key, self._sid, self._wrapped = key, sid, wrapped
        self._pid, self._seq = _sl_os.getpid(), 0

    def emit_bytes(self, raw: bytes) -> bool:
        """False => dropped; NEVER return to plaintext on a crypto/output error."""
        try:
            with self._lock:
                if self._pid != _sl_os.getpid() or self._seq >= 2**63 - 1:
                    self._new_session()
                self._seq += 1  # Consume the sequence even if later work fails.
                seq = self._seq
                if not isinstance(raw, bytes):
                    raise TypeError('bytes required')
                body = _sl_pack_plain(raw)
                # Every record includes its wrapped session key; no lone key header.
                header = (_SL_MAGIC + self._kid + self._sid + seq.to_bytes(8, 'big') +
                          len(self._wrapped).to_bytes(2, 'big') + self._wrapped +
                          (len(body) + 16).to_bytes(4, 'big'))
                nonce = seq.to_bytes(12, 'big')
                packet = header + _sl_seal(self._key, nonce, body, header)
                encoded = _sl_b64.b64encode(packet).decode('ascii')
                count = (len(encoded) + _SL_CHUNK - 1) // _SL_CHUNK
                for index in range(count):
                    chunk = encoded[index * _SL_CHUNK:(index + 1) * _SL_CHUNK]
                    self._sink(f'{_SL_PREFIX}{self._sid.hex()} {seq} {index + 1}/{count} {chunk}')
                return True
        except Exception:
            # Do not include raw, exception messages, keys or strategy function names.
            self._failures += 1
            if self._failures == 1 or self._failures % 128 == 0:
                try:
                    self._sink('[_sl_emit_line] SECURE_LOG_DROPPED')
                except Exception:
                    pass
            return False

    def emit_text(self, text: str) -> bool:
        try:
            if not isinstance(text, str) or len(text) > _SL_MAX_RAW:
                raise ValueError('invalid log text')
            return self.emit_bytes(text.encode('utf-8'))
        except Exception:
            # Reuse the protected failure path, never print text.
            return self.emit_bytes(None)

    def print(self, *objects, sep=' ', end='\n', file=None, flush=True):
        """Compatibility for the two audited stdout diagnostic call sites only."""
        try:
            if file is not None:
                raise ValueError('non-stdout target not supported')
            sep = ' ' if sep is None else sep
            end = '\n' if end is None else end
            if not isinstance(sep, str) or not isinstance(end, str):
                raise TypeError('invalid print options')
            text = sep.join(str(item) for item in objects) + end
            self.emit_text(text)
        except Exception:
            self.emit_bytes(None)
        return None
