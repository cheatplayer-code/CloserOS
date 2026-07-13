#!/usr/bin/env python3
"""Offline validator for GitHub Actions supply-chain pins.

Every external ``uses:`` reference in ``.github/workflows`` must be pinned to a
40-character lowercase commit SHA that matches an entry in
``.github/action-pins.json``. Repository-local ``./`` actions are allowed and
skipped. This validator runs without network access: remote existence of each
pin is proven separately with ``git ls-remote`` and recorded in the pin file.
The validator's job is to prevent future accidental, mutable, or hallucinated
references from re-entering the workflows.

Exit code ``0`` means every reference is valid; ``1`` means at least one
violation was found and printed to stderr.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
PINS_FILE = REPO_ROOT / ".github" / "action-pins.json"

# Matches a ``uses:`` line and captures the reference token, stopping before any
# trailing whitespace, inline comment, or surrounding quote.
_USES_RE = re.compile(r"""^\s*(?:-\s+)?uses:\s*['"]?(?P<ref>[^'"\s#]+)""")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_LOCAL_PREFIXES = ("./", "../")


def _iter_workflow_files(workflows_dir: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.yml", "*.yaml"):
        files.extend(workflows_dir.glob(pattern))
    return sorted(files)


def _repository_key(reference_before_at: str) -> str:
    """Return the ``owner/repo`` key for an action reference path.

    ``anchore/scan-action/download@<sha>`` maps to ``anchore/scan-action``.
    """

    parts = reference_before_at.split("/")
    return "/".join(parts[:2])


def load_pins(pins_file: Path = PINS_FILE) -> dict[str, str]:
    """Load and structurally validate the committed pin file.

    Returns a mapping of ``owner/repo`` to the expected commit SHA. Raises
    ``ValueError`` on malformed content so callers can surface a clear error.
    """

    raw = pins_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    actions = data.get("actions")
    if not isinstance(actions, dict):
        raise ValueError("action-pins.json must contain an 'actions' object")

    pins: dict[str, str] = {}
    for name, entry in actions.items():
        if name in pins:
            raise ValueError(f"duplicate pin definition for {name}")
        if not isinstance(entry, dict):
            raise ValueError(f"pin entry for {name} must be an object")
        sha = entry.get("sha")
        if not isinstance(sha, str) or not _SHA_RE.match(sha):
            raise ValueError(f"pin for {name} must have a 40-char lowercase hex sha")
        if not isinstance(entry.get("tag"), str) or not entry["tag"]:
            raise ValueError(f"pin for {name} must record a human-readable tag")
        pins[name] = sha
    return pins


def collect_uses_references(workflows_dir: Path = WORKFLOWS_DIR) -> list[tuple[str, int, str]]:
    """Return ``(workflow_name, line_number, reference)`` for every uses line."""

    references: list[tuple[str, int, str]] = []
    for path in _iter_workflow_files(workflows_dir):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _USES_RE.match(line)
            if match:
                references.append((path.name, line_number, match.group("ref")))
    return references


def validate(
    workflows_dir: Path = WORKFLOWS_DIR,
    pins_file: Path = PINS_FILE,
) -> list[str]:
    """Validate all workflow ``uses:`` references. Return a list of error strings."""

    errors: list[str] = []

    try:
        pins = load_pins(pins_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot load {pins_file.name}: {exc}"]

    observed: dict[str, str] = {}

    for workflow, line_number, reference in collect_uses_references(workflows_dir):
        location = f"{workflow}:{line_number}"

        if reference.startswith(_LOCAL_PREFIXES):
            continue

        if "@" not in reference:
            errors.append(
                f"{location}: external reference '{reference}' is not pinned to a commit SHA"
            )
            continue

        path_part, _, ref_part = reference.partition("@")
        key = _repository_key(path_part)

        if not _SHA_RE.match(ref_part):
            errors.append(
                f"{location}: '{reference}' uses a mutable or non-SHA ref; "
                "a 40-char lowercase commit SHA is required"
            )
            continue

        if key not in pins:
            errors.append(
                f"{location}: '{key}' is not present in action-pins.json (unknown external action)"
            )
            continue

        if pins[key] != ref_part:
            errors.append(
                f"{location}: '{key}' pinned to {ref_part} but action-pins.json expects {pins[key]}"
            )
            continue

        previous = observed.get(key)
        if previous is not None and previous != ref_part:
            errors.append(
                f"{location}: '{key}' referenced with conflicting SHAs {previous} and {ref_part}"
            )
        observed[key] = ref_part

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Action pin validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Action pin validation passed: all external references match action-pins.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
