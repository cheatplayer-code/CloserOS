"""Static tests for GitHub Actions supply-chain and container workflow policy."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.ci.validate_action_pins import (
    collect_uses_references,
    load_pins,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
CONTAINERS_WORKFLOW = WORKFLOWS_DIR / "containers.yml"
QUALITY_WORKFLOW = WORKFLOWS_DIR / "quality.yml"
PINS_FILE = REPO_ROOT / ".github" / "action-pins.json"
SECURITY_TOOLS_LOCK = REPO_ROOT / "scripts" / "ci" / "security-tools.lock"
INSTALL_SECURITY_TOOLS = REPO_ROOT / "scripts" / "ci" / "install_security_tools.sh"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CREDENTIALED_URI_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^[:space:]/]+:[^[:space:]@]+@")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _workflow_text(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _containers_text() -> str:
    return CONTAINERS_WORKFLOW.read_text(encoding="utf-8")


def _quality_text() -> str:
    return QUALITY_WORKFLOW.read_text(encoding="utf-8")


def test_action_pin_validator_passes_offline() -> None:
    assert validate() == []


def test_all_external_actions_use_40_char_sha() -> None:
    for workflow, line_number, reference in collect_uses_references(WORKFLOWS_DIR):
        if reference.startswith("./"):
            continue
        assert "@" in reference, f"{workflow}:{line_number} is not pinned"
        _, _, ref_part = reference.partition("@")
        assert _SHA_RE.match(ref_part), (
            f"{workflow}:{line_number} uses mutable or invalid ref '{ref_part}'"
        )


def test_workflow_pins_match_action_pins_json() -> None:
    pins = load_pins(PINS_FILE)
    for workflow, line_number, reference in collect_uses_references(WORKFLOWS_DIR):
        if reference.startswith("./"):
            continue
        path_part, _, ref_part = reference.partition("@")
        key = "/".join(path_part.split("/")[:2])
        assert pins[key] == ref_part, (
            f"{workflow}:{line_number}: {key} pinned to {ref_part}, "
            f"action-pins.json expects {pins[key]}"
        )


def test_action_pins_json_has_no_duplicate_entries() -> None:
    raw = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    actions = raw["actions"]
    assert len(actions) == len(set(actions))


def test_containers_workflow_has_no_trivy_action_wrapper() -> None:
    text = _containers_text()
    assert "aquasecurity/trivy-action" not in text
    assert "aquasecurity/setup-trivy" not in text


def test_containers_workflow_has_no_docker_action_wrappers() -> None:
    text = _containers_text()
    forbidden = (
        "docker/setup-buildx-action",
        "docker/build-push-action",
        "docker/login-action",
        "anchore/sbom-action",
    )
    for action in forbidden:
        assert action not in text, f"forbidden action wrapper present: {action}"


def test_containers_workflow_retains_only_checkout_and_upload_artifact() -> None:
    external = {
        reference
        for workflow, _, reference in collect_uses_references(WORKFLOWS_DIR)
        if workflow == "containers.yml" and not reference.startswith("./")
    }
    expected = {
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    }
    assert external == expected


def test_publish_on_tag_needs_build_and_scan() -> None:
    text = _containers_text()
    publish_start = text.index("  publish-on-tag:")
    publish_block = text[publish_start:]
    assert "needs:" in publish_block
    assert "build-and-scan" in publish_block


def test_publish_on_tag_has_packages_write_only_on_publish_job() -> None:
    text = _containers_text()
    publish_start = text.index("  publish-on-tag:")
    publish_block = text[publish_start:]
    assert "packages: write" in publish_block
    build_start = text.index("  build-and-scan:")
    build_block = text[build_start:publish_start]
    assert "packages: write" not in build_block


def test_publish_on_tag_skipped_on_pull_request() -> None:
    text = _containers_text()
    assert "if: startsWith(github.ref, 'refs/tags/v')" in text
    assert "pull_request:" in text


def test_publish_on_tag_does_not_publish_latest() -> None:
    text = _containers_text()
    assert ":latest" not in text


def test_security_tools_lock_pins_versions_and_sha256() -> None:
    values: dict[str, str] = {}
    for line in SECURITY_TOOLS_LOCK.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition("=")
        values[key] = value

    assert values["SYFT_VERSION"] == "1.46.0"
    assert values["GRYPE_VERSION"] == "0.115.0"
    assert _SHA256_RE.match(values["SYFT_LINUX_AMD64_SHA256"])
    assert _SHA256_RE.match(values["GRYPE_LINUX_AMD64_SHA256"])


def test_install_security_tools_verifies_checksum_before_extract() -> None:
    text = INSTALL_SECURITY_TOOLS.read_text(encoding="utf-8")
    assert "sha256sum --check" in text
    assert "tar -xzf" in text
    assert text.index("sha256sum --check") < text.index("tar -xzf")
    assert "curl | sh" not in text.replace(" ", "")


def test_quality_workflow_has_no_complete_credentialed_database_url_literal() -> None:
    text = _quality_text()
    assert "TEST_DATABASE_URL:" not in text
    assert "TEST_DB_SCHEME:" in text
    assert "TEST_DB_PASSWORD:" in text
    assert "printf 'TEST_DATABASE_URL=%s://%s:%s@%s:%s/%s\\n'" in text
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        assert not _CREDENTIALED_URI_RE.search(line), (
            f"quality.yml contains a complete credentialed URI literal: {line.strip()}"
        )


def test_containers_workflow_uses_direct_buildx_cli() -> None:
    text = _containers_text()
    assert "docker buildx create" in text
    assert "docker buildx build" in text
    assert "docker buildx rm" in text


def test_containers_workflow_uses_standalone_syft_and_grype() -> None:
    text = _containers_text()
    assert "install_security_tools.sh" in text
    assert 'syft scan "docker:${IMAGE_TAG}"' in text
    assert 'grype "docker:${IMAGE_TAG}"' in text
    assert "--only-fixed" in text
    assert "--fail-on high" in text


def test_containers_workflow_uses_grype_exceptions_config() -> None:
    text = _containers_text()
    assert "validate_grype_exceptions.py" in text
    assert "--config scripts/ci/grype-exceptions.yaml" in text
    assert "--only-fixed" in text
    assert "--fail-on high" in text


def test_containers_workflow_uploads_combined_security_artifacts() -> None:
    text = _containers_text()
    assert "container-security-${{ matrix.name }}" in text
    assert "artifacts/sbom-${{ matrix.name }}.spdx.json" in text
    assert "artifacts/vulnerability-${{ matrix.name }}.json" in text
