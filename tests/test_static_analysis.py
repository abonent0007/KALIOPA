"""Самопроверка статического анализатора: он должен ловить то, ради чего он есть.

Инструмент `tools/static_analysis.py` заменяет отсутствующие в окружении
линтеры, поэтому его собственные правила тоже нужно держать под тестом:
неиспользуемый импорт, статический URL, внешний вызов без try и корректное
игнорирование `__future__` / реэкспортов из `__init__.py`.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "tools"))

import static_analysis  # noqa: E402


class StaticAnalysisTests(unittest.TestCase):
    def test_detects_unused_import(self):
        report = static_analysis.analyze_source("import json\nx = 1\n", "sample.py")
        self.assertEqual([{"line": 1, "name": "json", "module": "json"}], report.unused_imports)

    def test_used_import_is_not_reported(self):
        report = static_analysis.analyze_source("import json\nprint(json.dumps({}))\n", "sample.py")
        self.assertEqual([], report.unused_imports)

    def test_future_annotations_is_ignored(self):
        report = static_analysis.analyze_source("from __future__ import annotations\n", "sample.py")
        self.assertEqual([], report.unused_imports)

    def test_package_reexports_are_ignored(self):
        report = static_analysis.analyze_source(
            "from .config import proxy_config\n", "__init__.py"
        )
        self.assertEqual([], report.unused_imports)

    def test_static_values_are_inventoried(self):
        source = 'URL = "https://example.com/api"\nPORT = 1370\nPATH = r"C:\\Temp\\x"\n'
        kinds = {item["kind"] for item in static_analysis.analyze_source(source, "s.py").static_values}
        self.assertEqual({"url", "number", "windows_path"}, kinds)

    def test_unguarded_external_call_is_reported(self):
        source = "import requests\ndef fetch():\n    return requests.get('https://example.com')\n"
        calls = static_analysis.analyze_source(source, "s.py").unguarded_calls
        self.assertEqual([{"line": 3, "call": "requests.get"}], calls)

    def test_guarded_external_call_is_not_reported(self):
        source = (
            "import requests\n"
            "def fetch():\n"
            "    try:\n"
            "        return requests.get('https://example.com')\n"
            "    except Exception:\n"
            "        return None\n"
        )
        self.assertEqual([], static_analysis.analyze_source(source, "s.py").unguarded_calls)


if __name__ == "__main__":
    unittest.main()
