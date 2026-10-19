"""Increment the fork build number in resources/nova_metadata.py."""

from __future__ import annotations

import os
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "resources" / "nova_metadata.py"
PATTERN = re.compile(r'CURRENT_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?"')


def bump(text: str) -> tuple[str, str]:
    match = PATTERN.search(text)
    if not match:
        raise ValueError("CURRENT_VERSION not found")
    major, minor, patch, build = match.groups()
    version = f"{major}.{minor}.{patch}.{int(build or 0) + 1}"
    updated = text[:match.start()] + f'CURRENT_VERSION = "{version}"' + text[match.end():]
    return updated, version


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    updated, version = bump(text)
    tmp = PATH.with_name(PATH.name + ".tmp")
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, PATH)
    print(version)


if __name__ == "__main__":
    main()
