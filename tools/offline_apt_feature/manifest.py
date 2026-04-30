"""Manifest generation and validation helpers."""

from datetime import UTC, datetime
from pathlib import Path
import hashlib
import json

from offline_apt_feature.models import Bundle
from offline_apt_feature.repo_index import deb_files, read_packages_gz


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(bundle: Bundle, architecture: str, repo_dir: Path) -> dict[str, object]:
    """Build a manifest for one generated architecture repository."""
    packages_index = repo_dir / "Packages.gz"
    if not packages_index.is_file():
        raise FileNotFoundError(f"missing Packages.gz: {packages_index}")

    records = read_packages_gz(packages_index)
    debs = deb_files(repo_dir)
    hashes = {path.name: sha256_file(path) for path in debs}
    source_path = repo_dir / "apt-sources.txt"
    source_text = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""

    return {
        "distro": bundle.distro,
        "codename": bundle.codename,
        "base_image": bundle.base_image,
        "architecture": architecture,
        "generated_at": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "requested_packages": [
            {"name": package.name, "version": package.version, "spec": package.spec()}
            for package in bundle.packages
        ],
        "resolved_deb_filenames": [path.name for path in debs],
        "resolved_packages": [
            {
                "name": record.package,
                "version": record.version,
                "architecture": record.architecture,
                "filename": record.deb_filename,
                "sha256": hashes.get(record.deb_filename, record.sha256),
                "size": record.size,
            }
            for record in records
        ],
        "sha256": hashes,
        "apt_source_metadata": {
            "resolver_image": bundle.base_image,
            "resolver_platform": f"linux/{architecture}",
            "source_files": source_text,
        },
    }


def write_manifest(bundle: Bundle, architecture: str, repo_dir: Path) -> Path:
    """Write a manifest.json file for one generated architecture repository."""
    manifest = build_manifest(bundle, architecture, repo_dir)
    path = repo_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_arch_manifest(bundle: Bundle, architecture: str, project_root: Path) -> dict[str, object]:
    """Load the generated manifest for one architecture."""
    path = bundle.repo_dir(project_root, architecture) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def resolved_version(manifest: dict[str, object], package_name: str) -> str:
    """Return the resolved version for a package in an architecture manifest."""
    packages = manifest.get("resolved_packages", [])
    if not isinstance(packages, list):
        raise ValueError("manifest resolved_packages must be a list")
    for package in packages:
        if isinstance(package, dict) and package.get("name") == package_name:
            version = package.get("version")
            if isinstance(version, str):
                return version
    raise ValueError(f"package {package_name} not found in manifest")
