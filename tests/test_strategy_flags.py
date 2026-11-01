"""Защита strat/*.json от опечаток в опциях winws.

winws молча падает, если в стратегии встречается неизвестная опция: стратегия
просто не запускается, а подбор (boost/learn) считает её нерабочей. Так в
`strat/strategies.json` жили `--dpi-desync-multisplit-threshold` и
`--dpi-desync-multisplit-re-inject` (опции nfqws, в winws их нет), а в
`strat/whatsapp.json` — устаревшая `--dpi-desync-split-tls`.

Список ниже сверен с docs/readme.md zapret v72.13 (bin/winws.exe) 2026-10-27.
Если добавляешь новую опцию — сначала проверь её в документации zapret,
потом добавь сюда.
"""

import json
import re
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

WINWS_OPTIONS = frozenset(
    {
        "--dpi-desync",
        "--dpi-desync-any-protocol",
        "--dpi-desync-autottl",
        "--dpi-desync-badseq-increment",
        "--dpi-desync-fake-http",
        "--dpi-desync-fake-quic",
        "--dpi-desync-fake-tls",
        "--dpi-desync-fake-tls-mod",
        "--dpi-desync-fakedsplit-pattern",
        "--dpi-desync-fooling",
        "--dpi-desync-hostfakesplit-mod",
        "--dpi-desync-repeats",
        "--dpi-desync-split-pos",
        "--dpi-desync-split-seqovl",
        "--dpi-desync-split-seqovl-pattern",
        "--dpi-desync-ttl",
        "--dup",
        "--dup-cutoff",
        "--dup-fooling",
        "--filter-l7",
        "--filter-tcp",
        "--filter-udp",
        "--new",
    }
)

FLAG_RE = re.compile(r"--[a-z0-9][a-z0-9-]{2,40}")


def iter_args(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_args(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_args(value)


class StrategyFlagTests(unittest.TestCase):
    def test_only_documented_winws_options(self):
        unknown = {}
        for path in sorted((BASE_DIR / "strat").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for arg in iter_args(data):
                for flag in FLAG_RE.findall(arg):
                    if flag not in WINWS_OPTIONS:
                        unknown.setdefault(flag, set()).add(path.name)

        self.assertEqual(
            {},
            {flag: sorted(files) for flag, files in sorted(unknown.items())},
            "неизвестные опции winws в strat/*.json",
        )


if __name__ == "__main__":
    unittest.main()
