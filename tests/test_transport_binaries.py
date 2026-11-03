"""Вендорные транспортные бинарники отвечают и называют ожидаемую версию."""

import subprocess
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
BIN = BASE_DIR / "bin"


def _run(*args, timeout=30):
    return subprocess.run(
        [str(part) for part in args],
        capture_output=True, text=True, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class TransportBinaryTests(unittest.TestCase):
    def _version(self, path, *args):
        if not Path(path).is_file():
            self.skipTest("%s отсутствует (bin/ не коммитится)" % path)
        result = _run(path, *args)
        self.assertEqual(0, result.returncode, result.stderr)
        return (result.stdout or result.stderr).strip()

    def test_nova_go_reports_a_version(self):
        text = self._version(BIN / "nova-go.exe", "version")
        self.assertRegex(text.splitlines()[0], r"^nova-go \d+\.\d+\.\d+\.\d+")

    def test_nova_xray_uses_the_pinned_core(self):
        text = self._version(BIN / "nova-xray.exe", "version")
        self.assertIn("xray-core 26.10.31", text.splitlines()[0])

    def test_wireproxy_awg_is_updated(self):
        text = self._version(BIN / "wireproxy-awg.exe", "--version")
        self.assertIn("1.0.18", text)

    def test_opera_proxy_is_updated(self):
        text = self._version(BIN / "opera-proxy.windows-amd64.exe", "--version")
        self.assertIn("1.31.0", text)

    def test_tor_bundle_is_updated(self):
        text = self._version(BIN / "tor" / "nova-tor.exe", "--version")
        self.assertIn("0.4.9.15", text)


if __name__ == "__main__":
    unittest.main()
