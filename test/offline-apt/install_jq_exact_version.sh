#!/usr/bin/env bash
set -euo pipefail

source dev-container-features-test-lib

expected="$(cat expected-jq-version)"
actual="$(dpkg-query -W -f='${Version}' jq)"

check "jq exact version" test "${actual}" = "${expected}"
check "architecture marker matches" bash -lc '[ "$(cat /usr/local/share/offline-apt-feature/selected-architecture)" = "$(dpkg --print-architecture)" ]'

reportResults
