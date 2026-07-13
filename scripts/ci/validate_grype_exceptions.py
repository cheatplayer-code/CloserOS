#!/usr/bin/env python3
"""Offline validator for reviewed Grype exception entries."""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GRYPE_EXCEPTIONS = REPO_ROOT / "scripts" / "ci" / "grype-exceptions.yaml"
GRYPE_METADATA = REPO_ROOT / "scripts" / "ci" / "grype-exceptions.meta.json"
_CVE_RE = re.compile(r"^CVE-\d{4}-\d+$")
_WILDCARD_RE = re.compile(r"[*?]")


def _parse_simple_yaml_ignore(path: Path) -> list[dict[str, str]]:
    """Parse the small ignore list without a YAML dependency."""

    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- vulnerability:"):
            if current is not None:
                entries.append(current)
            current = {"vulnerability": line.split(":", 1)[1].strip()}
            continue
        if current is None:
            continue
        if line.startswith("name:"):
            current["package_name"] = line.split(":", 1)[1].strip()
        elif line.startswith("version:"):
            current["package_version"] = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("reason:"):
            current["reason"] = line.split(":", 1)[1].strip().lstrip(">-").strip()
        elif line.startswith("expires-on:"):
            current["expires_on"] = line.split(":", 1)[1].strip().strip('"')
        elif (
            current.get("reason") is not None
            and current.get("expires_on") is None
            and not line.startswith(("name:", "version:", "- vulnerability:"))
        ):
            current["reason"] = f"{current['reason']} {line}".strip()
    if current is not None:
        entries.append(current)
    return entries


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def validate(
    exceptions_file: Path = GRYPE_EXCEPTIONS,
    metadata_file: Path = GRYPE_METADATA,
    *,
    today: date | None = None,
) -> list[str]:
    errors: list[str] = []
    reference_day = today or date.today()

    if not exceptions_file.is_file():
        return [f"missing {exceptions_file.relative_to(REPO_ROOT)}"]

    yaml_entries = _parse_simple_yaml_ignore(exceptions_file)
    if not yaml_entries:
        return ["grype-exceptions.yaml must contain at least one reviewed entry"]

    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot load grype-exceptions.meta.json: {exc}"]

    meta_entries = metadata.get("entries")
    if not isinstance(meta_entries, list):
        return ["grype-exceptions.meta.json must contain an 'entries' array"]

    meta_by_cve = {
        entry["vulnerability"]: entry for entry in meta_entries if "vulnerability" in entry
    }

    for entry in yaml_entries:
        cve = entry.get("vulnerability", "")
        if not _CVE_RE.match(cve):
            errors.append(f"invalid CVE identifier: {cve!r}")
        if _WILDCARD_RE.search(cve):
            errors.append(f"wildcard CVE entry is forbidden: {cve}")

        package_name = entry.get("package_name", "")
        package_version = entry.get("package_version", "")
        if not package_name or _WILDCARD_RE.search(package_name):
            errors.append(f"{cve}: package name must be exact")
        if not package_version or _WILDCARD_RE.search(package_version):
            errors.append(f"{cve}: package version must be exact")

        reason = entry.get("reason", "")
        if len(reason) < 40:
            errors.append(f"{cve}: reason must document reachability justification")

        expires_raw = entry.get("expires_on", "")
        try:
            expires_on = _parse_date(expires_raw)
        except ValueError:
            errors.append(f"{cve}: invalid expires-on date {expires_raw!r}")
            continue

        if expires_on < reference_day:
            errors.append(f"{cve}: expired on {expires_raw}")

        meta = meta_by_cve.get(cve)
        if meta is None:
            errors.append(f"{cve}: missing metadata entry")
            continue

        created_raw = meta.get("created_on", "")
        try:
            created_on = _parse_date(created_raw)
        except ValueError:
            errors.append(f"{cve}: invalid created_on in metadata")
            created_on = reference_day

        if (expires_on - created_on).days > 30:
            errors.append(f"{cve}: expiry exceeds 30-day review window")

        images = meta.get("images")
        if not isinstance(images, list) or not images:
            errors.append(f"{cve}: metadata must list affected images")
        elif any(_WILDCARD_RE.search(str(image)) for image in images):
            errors.append(f"{cve}: image selectors must be exact")

        if not meta.get("evidence"):
            errors.append(f"{cve}: metadata must reference evidence")
        if not meta.get("owner"):
            errors.append(f"{cve}: metadata must name an owner")

    if len(yaml_entries) != len(meta_entries):
        errors.append("yaml ignore entries and metadata entries must match in count")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Grype exception validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Grype exception validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
