# offline-apt-devcontainer-feature

## What this is

This is a proof-of-concept Dev Container Feature that carries a curated,
immutable Debian trixie apt shard inside the Feature OCI artifact.

The POC publishes this Feature shape:

```text
ghcr.io/jooh/offline-apt-devcontainer-feature/offline-apt:trixie-slim-v1
```

Example use:

```json
{
  "image": "debian:trixie-slim",
  "features": {
    "ghcr.io/jooh/offline-apt-devcontainer-feature/offline-apt:trixie-slim-v1": {
      "packages": "jq,ripgrep"
    }
  }
}
```

## Why this exists

Some dev container environments need repeatable package installs after the
Feature artifact is already available, without depending on live Debian apt
repositories during container build. This repository packages the minimal
offline apt content needed for a curated package set.

This is not a full Artifactory replacement. It is a curated immutable offline
apt shard packaged as a Dev Container Feature.

## How the Feature works

`bundle.yaml` declares one Debian trixie bundle for `debian:trixie-slim` and
two architectures: `amd64` and `arm64`.

`uv run offline-apt-feature build --bundle bundle.yaml` resolves the top-level package
list inside clean `debian:trixie-slim` containers for each architecture. The
generated Feature payload contains:

```text
src/offline-apt/repo/debian/trixie/amd64/
src/offline-apt/repo/debian/trixie/arm64/
```

Each architecture directory contains `.deb` files, `Packages.gz`, and
`manifest.json` after a build.

At install time, `install.sh`:

- requires `VERSION_CODENAME=trixie`
- detects `dpkg --print-architecture`
- selects only the matching local repo directory
- validates `packages` as comma-separated safe apt specs
- configures a temporary `file:` apt source
- installs only the requested packages plus dependencies
- removes apt list files and temporary apt source configuration

Feature options are intentionally limited to strings and booleans. Package
input is a comma-separated string:

```json
{
  "packages": "jq,ripgrep,shellcheck=0.10.0-1",
  "strict": true
}
```

## How to add packages

Edit `bundle.yaml`:

```yaml
packages:
  - name: jq
    version: null
  - name: ripgrep
    version: null
  - name: shellcheck
    version: null
```

`version: null` resolves the default candidate from Debian trixie apt sources.
A non-null version is rendered as `package=version` during resolution.

Then rebuild:

```bash
uv sync
uv run offline-apt-feature validate --bundle bundle.yaml
uv run offline-apt-feature build --bundle bundle.yaml
uv run python tools/validate_manifest.py --bundle bundle.yaml
```

## How to build the bundled repo

Prerequisites:

- uv with Python 3.12+
- Docker with Buildx
- QEMU/binfmt support when building the non-native architecture

Build:

```bash
uv sync
uv run offline-apt-feature build --bundle bundle.yaml
```

The generated `.deb`, `Packages.gz`, and `manifest.json` files are ignored by
git. They are build artifacts that get included when the Feature is packaged.

## How to test locally on macOS

On Apple Silicon, Docker Desktop or a compatible engine can run the native
`arm64` tests directly. Enable QEMU/binfmt if you also want local `amd64`
coverage.

```bash
uv sync
uv run offline-apt-feature build --bundle bundle.yaml
tools/run_feature_tests.sh arm64
tools/run_feature_tests.sh amd64
tools/run_failure_tests.sh
```

The test scripts use `uv run devcontainer`; `devcontainer-rs` is installed from
PyPI through the project environment. The exact-version test is rendered from
the generated manifest before each architecture test run.

## How to publish to GHCR

The CI workflow publishes on `main` and tags. It runs:

```bash
uv run devcontainer features publish ./src/offline-apt \
  --registry ghcr.io \
  --namespace "$GITHUB_REPOSITORY"
```

`devcontainer-rs` currently writes a local OCI layout. The workflow then copies
that layout to GHCR with ORAS and applies both the Feature implementation tag
and the bundle compatibility tag:

```bash
oras cp --from-oci-layout \
  "src/feature-oci-layout:1.0.0" \
  "ghcr.io/$GITHUB_REPOSITORY/offline-apt:1.0.0,trixie-slim-v1"
```

The Feature metadata version remains `1.0.0`; the OCI tag communicates the
distro/base compatibility target.

## How vulnerability scanning works

The workflow builds temporary monster images for each architecture:

```text
offline-apt-scan:trixie-slim-v1-amd64
offline-apt-scan:trixie-slim-v1-arm64
```

Each scan image starts from `debian:trixie-slim`, copies only the matching local
repo, configures a strict local `file:` apt source, and installs all top-level
packages from the manifest. Trivy scans those images and fails on
`HIGH,CRITICAL` by default. The threshold is configurable through the workflow
dispatch input or `TRIVY_SEVERITY`.

The workflow also runs `trivy fs .` for basic repository filesystem,
misconfiguration, and secret scanning.

## Limitations

- Debian trixie only.
- `amd64` and `arm64` only.
- Dependency closure is relative to `debian:trixie-slim`.
- The local apt repo uses `trusted=yes`.
- The POC publishes one Feature artifact containing both architecture repos.
- Package conflicts are not solved beyond normal apt behavior.
- Generated package artifacts are not committed by default.
- This is not an apt mirror, package proxy, or Artifactory replacement.

## Production-hardening backlog

- Sign the local apt repo instead of using `trusted=yes`.
- Sign GHCR artifacts with cosign.
- Add SBOM generation.
- Add provenance/attestation.
- Support more Debian/Ubuntu releases.
- Support base-image-specific variants.
- Improve dependency closure using an empty dpkg status database.
- Add Renovate or scheduled rebuilds for package refreshes.
- Split scan images if package sets conflict.
- Add policy files for allowed package names and versions.
- Add internal registry mirror support.
- Add generated package catalog docs from `manifest.json`.
