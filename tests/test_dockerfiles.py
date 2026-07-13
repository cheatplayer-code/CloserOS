"""Static policy tests for production Dockerfiles."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = REPO_ROOT / "infra" / "docker"
BASE_IMAGES_LOCK = DOCKER_DIR / "base-images.lock"
GRYPE_EXCEPTIONS = REPO_ROOT / "scripts" / "ci" / "grype-exceptions.yaml"

_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}")
_FROM_RE = re.compile(r"^FROM\s+(\S+)", re.MULTILINE)


def _load_base_images() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in BASE_IMAGES_LOCK.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition("=")
        values[key] = value
    return values


def _dockerfile(name: str) -> str:
    return (DOCKER_DIR / name).read_text(encoding="utf-8")


def _runtime_stage(text: str) -> str:
    parts = re.split(r"(?=^FROM\s+)", text, flags=re.MULTILINE)
    return parts[-1]


def test_python_version_matches_project_configuration() -> None:
    python_version = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    base_images = _load_base_images()
    expected_ref = f"python:{base_images['PYTHON_IMAGE_TAG']}@{base_images['PYTHON_IMAGE_DIGEST']}"

    for dockerfile_name in ("Dockerfile.api", "Dockerfile.worker"):
        text = _dockerfile(dockerfile_name)
        assert python_version in text
        assert text.count(expected_ref) == 2
        assert f"python:{python_version}-slim-bookworm" in text


def test_all_production_base_images_use_immutable_digests() -> None:
    base_images = _load_base_images()
    expectations = {
        "Dockerfile.api": (
            f"python:{base_images['PYTHON_IMAGE_TAG']}@{base_images['PYTHON_IMAGE_DIGEST']}",
            2,
        ),
        "Dockerfile.worker": (
            f"python:{base_images['PYTHON_IMAGE_TAG']}@{base_images['PYTHON_IMAGE_DIGEST']}",
            2,
        ),
        "Dockerfile.web": (
            f"node:{base_images['NODE_IMAGE_TAG']}@{base_images['NODE_IMAGE_DIGEST']}",
            2,
        ),
    }
    for dockerfile_name, (image_ref, count) in expectations.items():
        text = _dockerfile(dockerfile_name)
        assert text.count(image_ref) == count
        assert len(_DIGEST_RE.findall(text)) >= count
        assert ":latest" not in text


def test_runtime_users_are_non_root() -> None:
    assert "USER closeros" in _dockerfile("Dockerfile.api")
    assert "USER closeros" in _dockerfile("Dockerfile.worker")
    assert "USER node" in _dockerfile("Dockerfile.web")


def test_web_runtime_uses_standalone_node_entrypoint() -> None:
    runtime = _runtime_stage(_dockerfile("Dockerfile.web"))
    assert 'CMD ["node", "apps/web/server.js"]' in runtime
    assert "pnpm install" not in runtime
    assert "corepack enable" not in runtime
    assert "corepack pnpm" not in runtime
    assert ".next/standalone" in _dockerfile("Dockerfile.web")


def test_web_runtime_removes_global_npm_tooling() -> None:
    runtime = _runtime_stage(_dockerfile("Dockerfile.web"))
    assert "/usr/local/lib/node_modules/npm" in runtime
    assert "/usr/local/bin/npm" in runtime
    assert "/usr/local/bin/npx" in runtime
    assert "/usr/local/bin/corepack" in runtime
    assert "rm -rf /usr/local/lib/node_modules/npm" in runtime


def test_runtime_stages_apply_debian_security_upgrades() -> None:
    for dockerfile_name in ("Dockerfile.api", "Dockerfile.worker", "Dockerfile.web"):
        runtime = _runtime_stage(_dockerfile(dockerfile_name))
        assert "apt-get upgrade -y --no-install-recommends" in runtime
        assert "rm -rf /var/lib/apt/lists/*" in runtime


def test_no_broad_grype_ignore_configured() -> None:
    text = GRYPE_EXCEPTIONS.read_text(encoding="utf-8")
    assert "*" not in text
    assert "?" not in text
