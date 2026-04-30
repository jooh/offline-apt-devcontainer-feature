"""Build temporary scan images that install all top-level bundled packages."""

from pathlib import Path
import shlex
import subprocess
import tempfile

from offline_apt_feature.manifest import load_arch_manifest
from offline_apt_feature.models import Bundle


def build_scan_image(bundle: Bundle, project_root: Path, architecture: str) -> str:
    """Build a monster scan image for one architecture and return its tag."""
    if architecture not in bundle.architectures:
        raise ValueError(f"architecture {architecture} is not listed in bundle.yaml")

    manifest = load_arch_manifest(bundle, architecture, project_root)
    requested = manifest.get("requested_packages", [])
    if not isinstance(requested, list):
        raise ValueError("manifest requested_packages must be a list")
    specs = [entry["spec"] for entry in requested if isinstance(entry, dict)]
    if not specs or not all(isinstance(spec, str) for spec in specs):
        raise ValueError("manifest requested_packages must include string specs")

    tag = f"offline-apt-scan:{bundle.tag}-{architecture}"
    feature_dir = bundle.feature_dir(project_root)
    with tempfile.TemporaryDirectory(prefix="offline-apt-scan-") as tmp:
        dockerfile = Path(tmp) / "Dockerfile"
        package_args = " ".join(shlex.quote(spec) for spec in specs)
        dockerfile.write_text(
            f"""FROM {bundle.base_image}
COPY repo/{bundle.distro}/{bundle.codename}/{architecture}/ /offline-apt-repo/
RUN set -eux; \\
    rm -f /etc/apt/sources.list; \\
    rm -f /etc/apt/sources.list.d/*; \\
    printf '%s\\n' 'deb [trusted=yes arch={architecture}] file:/offline-apt-repo ./' > /etc/apt/sources.list.d/offline-apt-local.list; \\
    apt-get update; \\
    apt-get install -y --no-install-recommends {package_args}; \\
    rm -rf /var/lib/apt/lists/*
""",
            encoding="utf-8",
        )
        run(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                f"linux/{architecture}",
                "--load",
                "--tag",
                tag,
                "--file",
                str(dockerfile),
                str(feature_dir),
            ],
            project_root,
        )
    return tag


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with checked status."""
    process = subprocess.run(
        command,
        cwd=cwd,
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
