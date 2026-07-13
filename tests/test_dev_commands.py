"""Static checks for root developer commands."""

from __future__ import annotations

import json
from pathlib import Path


def test_dev_worker_uses_all_mode() -> None:
    package_json = json.loads(Path("package.json").read_text(encoding="utf-8"))
    scripts = package_json.get("scripts", {})
    assert scripts.get("dev:worker") == "uv run closeros-worker all"
