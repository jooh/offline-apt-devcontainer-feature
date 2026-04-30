#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  echo "offline-apt: $*" >&2
  exit 1
}

if [ ! -f /etc/os-release ]; then
  fail "missing /etc/os-release"
fi

# shellcheck disable=SC1091
. /etc/os-release

if [ "${VERSION_CODENAME:-}" != "trixie" ]; then
  fail "only Debian trixie is supported; found VERSION_CODENAME=${VERSION_CODENAME:-unknown}"
fi

if ! command -v dpkg >/dev/null 2>&1; then
  fail "dpkg is required"
fi

arch="$(dpkg --print-architecture)"
case "${arch}" in
  amd64 | arm64) ;;
  *) fail "unsupported architecture: ${arch}" ;;
esac

feature_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="${feature_dir}/repo/debian/trixie/${arch}"
if [ ! -d "${repo_dir}" ]; then
  fail "missing bundled apt repository for ${arch}: ${repo_dir}"
fi
if [ ! -f "${repo_dir}/Packages.gz" ]; then
  fail "missing bundled apt repository index for ${arch}: ${repo_dir}/Packages.gz"
fi

packages_raw="${PACKAGES:-}"
if [ -z "${packages_raw}" ]; then
  fail 'Feature option "packages" must be a non-empty comma-separated string'
fi

IFS=',' read -r -a raw_specs <<< "${packages_raw}"
package_specs=()
for raw_spec in "${raw_specs[@]}"; do
  if [ -z "${raw_spec}" ]; then
    fail "empty package spec in: ${packages_raw}"
  fi
  if [[ ! "${raw_spec}" =~ ^[a-z0-9][a-z0-9+.-]*([=][A-Za-z0-9][A-Za-z0-9.+:~_-]*)?$ ]]; then
    fail "Invalid package spec: ${raw_spec}"
  fi
  package_specs+=("${raw_spec}")
done

strict_raw="${STRICT:-true}"
case "${strict_raw}" in
  true | TRUE | 1 | yes | YES) strict="true" ;;
  false | FALSE | 0 | no | NO) strict="false" ;;
  *) fail "strict must be true or false; found: ${strict_raw}" ;;
esac

export DEBIAN_FRONTEND=noninteractive

tmp_dir="$(mktemp -d)"
source_file=""

cleanup() {
  if [ -n "${source_file}" ]; then
    rm -f "${source_file}"
  fi
  rm -rf "${tmp_dir}"
  rm -rf /var/lib/apt/lists/*
}
trap cleanup EXIT

repo_uri="file:${repo_dir}"
source_line="deb [trusted=yes arch=${arch}] ${repo_uri} ./"

apt_options=()
if [ "${strict}" = "true" ]; then
  mkdir -p "${tmp_dir}/lists/partial"
  printf '%s\n' "${source_line}" > "${tmp_dir}/sources.list"
  apt_options=(
    -o "Dir::Etc::sourcelist=${tmp_dir}/sources.list"
    -o "Dir::Etc::sourceparts=-"
    -o "Dir::State::Lists=${tmp_dir}/lists"
    -o "APT::Get::List-Cleanup=0"
  )
else
  source_file="/etc/apt/sources.list.d/offline-apt-local.list"
  printf '%s\n' "${source_line}" > "${source_file}"
fi

apt-get "${apt_options[@]}" update
apt-get "${apt_options[@]}" install -y --no-install-recommends "${package_specs[@]}"

install -d /usr/local/share/offline-apt-feature
printf '%s\n' "${arch}" > /usr/local/share/offline-apt-feature/selected-architecture
