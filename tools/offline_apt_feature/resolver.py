"""Architecture-specific apt dependency resolution."""

from pathlib import Path
import os
import shutil
import stat
import subprocess
import tempfile

from offline_apt_feature.manifest import write_manifest
from offline_apt_feature.models import Bundle
from offline_apt_feature.repo_index import deb_files


def build_bundle(bundle: Bundle, project_root: Path) -> list[Path]:
    """Build all architecture-specific flat apt repositories."""
    manifests: list[Path] = []
    for architecture in bundle.architectures:
        manifests.append(build_arch_repo(bundle, project_root, architecture))
    return manifests


def build_arch_repo(bundle: Bundle, project_root: Path, architecture: str) -> Path:
    """Build one architecture-specific flat apt repository."""
    if architecture not in bundle.architectures:
        raise ValueError(f"architecture {architecture} is not listed in bundle.yaml")

    repo_dir = bundle.repo_dir(project_root, architecture)
    repo_dir.mkdir(parents=True, exist_ok=True)
    clean_repo_dir(repo_dir)

    with tempfile.TemporaryDirectory(prefix="offline-apt-resolver-") as tmp:
        script_path = write_resolver_script(Path(tmp))
        command = [
            "docker",
            "run",
            "--rm",
            "--platform",
            f"linux/{architecture}",
            "-v",
            f"{repo_dir.resolve()}:/out",
            "-v",
            f"{script_path}:/resolver.sh:ro",
            bundle.base_image,
            "/bin/bash",
            "/resolver.sh",
            "/out",
            *bundle.top_level_specs(),
        ]
        run(command, project_root)

    if not deb_files(repo_dir):
        raise RuntimeError(f"resolver produced no .deb files in {repo_dir}")
    if not (repo_dir / "Packages.gz").is_file():
        raise RuntimeError(f"resolver did not produce Packages.gz in {repo_dir}")
    return write_manifest(bundle, architecture, repo_dir)


def clean_repo_dir(repo_dir: Path) -> None:
    """Remove generated files from an architecture repository directory."""
    for path in repo_dir.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def write_resolver_script(directory: Path) -> Path:
    """Write the container-side resolver script into a temporary directory."""
    script = directory / "resolver.sh"
    script.write_text(
        """#!/usr/bin/env bash
set -Eeuo pipefail

out="$1"
shift

export DEBIAN_FRONTEND=noninteractive

apt-get update

rm -f "${out}"/*.deb "${out}"/Packages "${out}"/Packages.gz "${out}"/manifest.json "${out}"/apt-sources.txt
rm -rf "${out}"/partial
apt-get clean

apt-get -o "Dir::Cache::archives=${out}" install -y --download-only --no-install-recommends "$@"
apt-get install -y --no-install-recommends dpkg-dev

rm -f "${out}"/lock
rm -rf "${out}"/partial

{
  if [ -f /etc/apt/sources.list ]; then
    printf '# /etc/apt/sources.list\\n'
    cat /etc/apt/sources.list
  fi
  if [ -d /etc/apt/sources.list.d ]; then
    find /etc/apt/sources.list.d -maxdepth 1 -type f -print | sort | while read -r source_file; do
      printf '\\n# %s\\n' "${source_file}"
      cat "${source_file}"
    done
  fi
} > "${out}/apt-sources.txt"

cd "${out}"
dpkg-scanpackages . /dev/null > Packages
gzip -9n < Packages > Packages.gz
rm -f Packages
""",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with captured text output and checked status."""
    env = os.environ.copy()
    process = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {process.returncode}: {' '.join(command)}\n"
            f"stdout:\n{process.stdout}\n\nstderr:\n{process.stderr}"
        )
    return process
