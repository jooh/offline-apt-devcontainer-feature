#!/usr/bin/env bash
set -euo pipefail

source dev-container-features-test-lib

check "jq exists" jq --version
check "ripgrep was not installed" bash -lc '! command -v rg >/dev/null 2>&1'
check "shellcheck was not installed" bash -lc '! dpkg-query -W shellcheck >/dev/null 2>&1'
check "architecture marker matches" bash -lc '[ "$(cat /usr/local/share/offline-apt-feature/selected-architecture)" = "$(dpkg --print-architecture)" ]'

reportResults
