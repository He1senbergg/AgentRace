import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('downloader', ROOT / 'auto_log_downloader.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DecryptTests(unittest.TestCase):
    def test_plaintext_kept(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / 'enemy.log'
            raw.write_bytes(b'ordinary log\n')
            with patch.object(m.subprocess, 'run') as run:
                self.assertEqual(m.decrypt_download(raw, {}), {'status': 'plaintext'})
                run.assert_not_called()
            self.assertEqual(list(Path(temp).iterdir()), [raw])

    def test_outputs_resume_repair_and_partial(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / 'ally_BlueSide_1_win.log'
            raw.write_bytes(b'prefix [_sl_emit_line] ASL1 ciphertext\n')
            saved = {'sha256': m.checksum(raw)}
            code = 0
            def decrypt(command, **kwargs):
                self.assertEqual(command[1], str(m.DECRYPT_TOOL))
                self.assertEqual(command[command.index('--private') + 1], str(m.PRIVATE_KEY))
                self.assertEqual(command[-2:], ['--backend', 'rsa'])
                out = Path(command[command.index('--out') + 1])
                self.assertFalse(out.exists())
                out.write_bytes(b'restored\n')
                Path(str(out) + '.report.json').write_text(json.dumps({'decoded_records': 1}))
                return subprocess.CompletedProcess(command, code, '', '')
            with patch.object(m.subprocess, 'run', side_effect=decrypt) as run:
                saved['decryption'] = m.decrypt_download(raw, saved)
                self.assertEqual(saved['decryption']['status'], 'ok')
                self.assertEqual(m.decrypt_download(raw, saved), saved['decryption'])
                self.assertEqual(run.call_count, 1)
                out = raw.with_name(raw.stem + '_decrypted.log')
                out.write_bytes(b'damaged')
                saved['decryption'] = m.decrypt_download(raw, saved)
                self.assertEqual(out.read_bytes(), b'restored\n')
                Path(str(out) + '.report.json').unlink()
                code = 2
                saved['decryption'] = m.decrypt_download(raw, saved)
                self.assertEqual(saved['decryption']['status'], 'partial')
                self.assertEqual(m.decrypt_download(raw, saved)['status'], 'partial')
                self.assertEqual(run.call_count, 3)
            self.assertEqual(len(list(Path(temp).iterdir())), 3)

    def test_fatal_preserves_raw_and_old_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / 'ally.log'
            raw.write_bytes(b'ASL1 bad\n')
            out = Path(temp) / 'ally_decrypted.log'
            out.write_bytes(b'previous')
            with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'missing key')):
                with self.assertRaisesRegex(RuntimeError, 'missing key'):
                    m.decrypt_download(raw, {'sha256': m.checksum(raw)})
            self.assertEqual(raw.read_bytes(), b'ASL1 bad\n')
            self.assertEqual(out.read_bytes(), b'previous')
            self.assertEqual(len(list(Path(temp).iterdir())), 2)


if __name__ == '__main__':
    unittest.main()
