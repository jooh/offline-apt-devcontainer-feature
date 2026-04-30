#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
arch="${1:?usage: tools/build_scan_image.sh <amd64|arm64>}"

cd "${repo_root}"
uv run offline-apt-feature build-scan-image --bundle bundle.yaml --arch "${arch}"
