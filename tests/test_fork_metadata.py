import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import bump_fork_version  # noqa: E402
import nova_metadata  # noqa: E402


class ForkMetadataTests(unittest.TestCase):
    def test_fork_version_is_numeric_four_part(self):
        self.assertRegex(nova_metadata.CURRENT_VERSION, r"^\d+\.\d+\.\d+\.\d+$")

    def test_program_update_check_is_disabled(self):
        self.assertEqual(nova_metadata.UPDATE_URL, "")

    def test_project_version_reads_fork_version(self):
        value = nova_metadata.read_project_version(
            Path(__file__).resolve().parents[1], default=""
        )
        self.assertEqual(value, nova_metadata.CURRENT_VERSION)

    def test_bump_increments_build_number(self):
        updated, version = bump_fork_version.bump('CURRENT_VERSION = "1.43.2.7"')
        self.assertEqual(version, "1.43.2.8")
        self.assertIn('CURRENT_VERSION = "1.43.2.8"', updated)


if __name__ == "__main__":
    unittest.main()
