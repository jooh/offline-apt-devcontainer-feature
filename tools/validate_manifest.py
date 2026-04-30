"""Validate generated offline apt manifests."""

from pathlib import Path
import json

import typer

from offline_apt_feature.manifest import sha256_file
from offline_apt_feature.models import load_bundle


app = typer.Typer(no_args_is_help=True)


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


@app.command()
def main(
    bundle: Path = typer.Option(Path("bundle.yaml"), "--bundle", exists=True, readable=True),
) -> None:
    """Validate generated manifests and referenced .deb hashes."""
    loaded = load_bundle(bundle)
    root = Path.cwd()
    for architecture in loaded.architectures:
        repo_dir = loaded.repo_dir(root, architecture)
        manifest_path = repo_dir / "manifest.json"
        packages_path = repo_dir / "Packages.gz"
        if not packages_path.is_file():
            _fail(f"missing {packages_path}")
        if not manifest_path.is_file():
            _fail(f"missing {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("architecture") != architecture:
            _fail(f"{manifest_path} has wrong architecture")
        hashes = manifest.get("sha256", {})
        if not isinstance(hashes, dict) or not hashes:
            _fail(f"{manifest_path} has no sha256 map")
        for filename, expected in hashes.items():
            deb_path = repo_dir / filename
            if not deb_path.is_file():
                _fail(f"missing .deb referenced by manifest: {deb_path}")
            actual = sha256_file(deb_path)
            if actual != expected:
                _fail(f"sha256 mismatch for {deb_path}")
        typer.echo(f"valid manifest: {manifest_path}")


if __name__ == "__main__":
    app()
