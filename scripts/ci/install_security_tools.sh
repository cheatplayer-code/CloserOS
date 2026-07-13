#!/usr/bin/env bash
#
# Install pinned standalone Syft and Grype binaries on a GitHub-hosted runner.
#
# The archive is downloaded from the official Anchore GitHub release assets over
# HTTPS and verified against the SHA-256 committed in security-tools.lock BEFORE
# extraction. A checksum mismatch aborts the install. Binaries are placed only
# inside $RUNNER_TEMP; nothing is written to system directories and sudo is not
# used. This script must run only on the CI runner, never on a laptop.

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/security-tools.lock"

: "${RUNNER_TEMP:?RUNNER_TEMP must be set; this installer runs only on GitHub-hosted runners}"

install_dir="$RUNNER_TEMP/closeros-security-tools"
mkdir -p "$install_dir"

download_and_verify() {
  local tool="$1"
  local version="$2"
  local expected_sha="$3"
  local asset="${tool}_${version}_linux_amd64.tar.gz"
  local url="https://github.com/anchore/${tool}/releases/download/v${version}/${asset}"
  local archive="$install_dir/${asset}"

  echo "Fetching ${tool} v${version} from official Anchore release assets"
  curl \
    --proto '=https' \
    --tlsv1.2 \
    --fail \
    --silent \
    --show-error \
    --location \
    --retry 3 \
    --retry-connrefused \
    --output "$archive" \
    "$url"

  echo "Verifying ${tool} archive against committed SHA-256"
  printf '%s  %s\n' "$expected_sha" "$archive" | sha256sum --check -

  echo "Extracting ${tool} binary"
  tar -xzf "$archive" -C "$install_dir" "$tool"
  rm -f "$archive"
}

download_and_verify "syft" "$SYFT_VERSION" "$SYFT_LINUX_AMD64_SHA256"
download_and_verify "grype" "$GRYPE_VERSION" "$GRYPE_LINUX_AMD64_SHA256"

if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$install_dir" >>"$GITHUB_PATH"
fi

"$install_dir/syft" version
"$install_dir/grype" version
