"""Каталог страновых точек входа: нормализация, разрешение, хранение."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "resources"))

import nova_warp_countries as countries  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_bad_rows_are_dropped(self):
        rows = countries.normalize([
            {"id": "FI", "title": "Финляндия", "host": "fi.example", "port": 500, "iso": "fi"},
            {"id": "", "title": "без id"},
            {"id": "BAD", "host": "bad host!", "port": 1},
            {"id": "X", "host": "ok.example", "port": "abc", "iso": "zzz"},
        ])
        ids = [row["id"] for row in rows]
        self.assertEqual(["any", "fi", "x"], ids)
        self.assertEqual("FI", rows[1]["iso"])
        self.assertEqual(0, rows[2]["port"])
        self.assertEqual("", rows[2]["iso"])

    def test_any_is_always_first(self):
        rows = countries.normalize([{"id": "de", "title": "Германия", "host": "de.example",
                                     "port": 500}])
        self.assertEqual("any", rows[0]["id"])

    def test_ids_are_slugified(self):
        row = countries.normalize_entry({"id": "LTE DE!", "title": "[LTE] Германия"})
        self.assertEqual("lte-de", row["id"])

    def test_cyrillic_title_gets_a_usable_slug(self):
        rid = countries.make_id("Финляндия")
        self.assertEqual("finlyandiya", rid)
        row = countries.normalize_entry({"id": rid, "title": "Финляндия",
                                         "host": "fi.example", "port": 500})
        self.assertIsNotNone(row)
        self.assertTrue(countries.make_id("").startswith("country-"))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.rows = countries.normalize([
            {"id": "any", "title": "Любая", "host": "", "port": 0},
            {"id": "fi", "title": "Финляндия", "host": "fi.example", "port": 500},
        ])

    def test_any_resolves_to_the_scanner(self):
        self.assertEqual(("", 0), countries.resolve(self.rows, "any"))
        self.assertEqual(("", 0), countries.resolve(self.rows, ""))
        self.assertEqual(("", 0), countries.resolve(self.rows, "unknown"))

    def test_country_resolves_to_its_endpoint(self):
        self.assertEqual(("fi.example", 500), countries.resolve(self.rows, "fi"))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="kaliopa-warp-countries-")

    def test_roundtrip(self):
        saved = countries.save(self.base, [
            {"id": "nl", "title": "Нидерланды", "host": "nl.example", "port": 500, "iso": "NL"},
        ])
        self.assertEqual(["any", "nl"], [row["id"] for row in saved])
        loaded = countries.load(self.base)
        self.assertEqual("nl.example", loaded[1]["host"])
        path = pathlib.Path(self.base) / "temp" / countries.FILENAME
        self.assertNotIn("PrivateKey", path.read_text(encoding="utf-8"))

    def test_missing_or_broken_file_is_not_an_error(self):
        self.assertEqual(["any"], [row["id"] for row in countries.load(self.base)])
        path = pathlib.Path(self.base) / "temp" / countries.FILENAME
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(["any"], [row["id"] for row in countries.load(self.base)])


class LabelTests(unittest.TestCase):
    def test_label_carries_host_and_port(self):
        text = countries.label({"id": "fi", "title": "Финляндия", "host": "fi.example", "port": 500})
        self.assertIn("fi.example:500", text)

    def test_any_label_says_scan(self):
        self.assertIn("авто-скан", countries.label({"id": "any", "title": "Любая"}))


if __name__ == "__main__":
    unittest.main()
