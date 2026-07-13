"""Reachability evidence for container CVE exceptions."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    REPO_ROOT / "apps" / "api" / "src",
    REPO_ROOT / "apps" / "worker" / "src",
    REPO_ROOT / "packages" / "backend" / "src",
)

_HTML_IMPORT_MARKERS = (
    "html.parser",
    "HTMLParser",
    "BeautifulSoup",
    "html5lib",
    "lxml",
)


def _python_sources(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def test_html_parser_not_used_in_runtime_paths() -> None:
    offenders: list[str] = []
    for root in RUNTIME_ROOTS:
        for path in _python_sources(root):
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in _HTML_IMPORT_MARKERS):
                offenders.append(str(path.relative_to(REPO_ROOT)))
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("html"):
                            offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("html")
                ):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert offenders == [], (
        "html parsing modules must not appear in API/worker runtime paths: " + ", ".join(offenders)
    )


def test_grype_exception_documents_cve_2026_15308_only() -> None:
    meta = (REPO_ROOT / "scripts" / "ci" / "grype-exceptions.meta.json").read_text(encoding="utf-8")
    assert "CVE-2026-15308" in meta
    assert meta.count("CVE-") == 1
