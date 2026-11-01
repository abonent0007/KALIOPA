"""Источник списка Opera: зеркала по умолчанию и внешний override."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_opera_feed as feed  # noqa: E402


class FeedUrlTests(unittest.TestCase):
    def test_mirrors_are_used_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(feed.FEED_URLS, feed.feed_urls())

    def test_external_source_goes_first(self):
        with mock.patch.dict(
            os.environ, {"NOVA_OPERA_ENDPOINTS_URL": "https://example.org/opera.json,https://b.example/x"}
        ):
            urls = feed.feed_urls()
        self.assertEqual("https://example.org/opera.json", urls[0])
        self.assertIn(feed.FEED_URLS[0], urls)

    def test_parse_survives_unknown_regions_and_junk(self):
        body = '{"regions": {"EU": ["1.2.3.4:443", "1.2.3.4:443"], "XX": ["5.6.7.8:1"]}}'
        self.assertEqual({"EU": ["1.2.3.4:443"]}, feed.parse_endpoint_feed(body))


if __name__ == "__main__":
    unittest.main()
