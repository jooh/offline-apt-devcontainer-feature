"""Typer command line interface for the offline apt Feature builder."""

from pathlib import Path
import json

import typer

from offline_apt_feature.manifest import load_arch_manifest, resolved_version
from offline_apt_feature.models import Bundle, load_bundle
from offline_apt_feature.resolver import build_bundle
from offline_apt_feature.scan import build_scan_image as build_scan_image_impl


app = typer.Typer(no_args_is_help=True)


def project_root() -> Path:
    """Return the current project root for command execution."""
    return Path.cwd()


@app.command()
def validate(
    bundle: Path = typer.Option(Path("bundle.yaml"), "--bundle", exists=True, readable=True),
) -> None:
    """Validate bundle.yaml and print a short summary."""
    loaded = load_bundle(bundle)
    typer.echo(
        f"valid bundle: {loaded.distro}/{loaded.codename} "
        f"{','.join(loaded.architectures)} {len(loaded.packages)} packages"
    )


@app.command("print-manifest")
def print_manifest(
    bundle: Path = typer.Option(Path("bundle.yaml"), "--bundle", exists=True, readable=True),
) -> None:
    """Print bundle metadata and any generated architecture manifests."""
    loaded = load_bundle(bundle)
    root = project_root()
    payload: dict[str, object] = {
        "bundle": loaded.model_dump(),
        "generated_manifests": {},
    }
    manifests = payload["generated_manifests"]
    if not isinstance(manifests, dict):
        raise RuntimeError("generated_manifests payload is not a dict")
    for architecture in loaded.architectures:
        path = loaded.repo_dir(root, architecture) / "manifest.json"
        if path.is_file():
            manifests[architecture] = json.loads(path.read_text(encoding="utf-8"))
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command()
def build(
    bundle: Path = typer.Option(Path("bundle.yaml"), "--bundle", exists=True, readable=True),
) -> None:
    """Build architecture-specific local apt repositories."""
    loaded = load_bundle(bundle)
    manifests = build_bundle(loaded, project_root())
    for manifest_path in manifests:
        typer.echo(f"wrote {manifest_path}")


@app.command("build-scan-image")
def build_scan_image(
    bundle: Path = typer.Option(Path("bundle.yaml"), "--bundle", exists=True, readable=True),
    arch: str = typer.Option(..., "--arch"),
) -> None:
    """Build a temporary monster image for Trivy scanning."""
    loaded = load_bundle(bundle)
    tag = build_scan_image_impl(loaded, project_root(), arch)
    typer.echo(tag)


@app.command("render-test-scenarios")
def render_test_scenarios(
    bundle: Path = typer.Option(Path("bundle.yaml"), "--bundle", exists=True, readable=True),
    arch: str = typer.Option("amd64", "--arch"),
) -> None:
    """Render Feature test scenarios using resolved manifest data."""
    loaded = load_bundle(bundle)
    if arch not in loaded.architectures:
        raise typer.BadParameter(f"architecture {arch} is not listed in bundle.yaml")
    root = project_root()
    manifest = load_arch_manifest(loaded, arch, root)
    jq_version = resolved_version(manifest, "jq")
    test_dir = root / "test" / loaded.feature_id
    test_dir.mkdir(parents=True, exist_ok=True)
    scenarios = feature_test_scenarios(loaded, jq_version)
    (test_dir / "scenarios.json").write_text(
        json.dumps(scenarios, indent=2) + "\n",
        encoding="utf-8",
    )
    (test_dir / "expected-jq-version").write_text(jq_version + "\n", encoding="utf-8")
    typer.echo(f"rendered scenarios for {arch} with jq={jq_version}")


def feature_test_scenarios(bundle: Bundle, jq_version: str) -> dict[str, object]:
    """Return devcontainer-rs Feature scenarios for success tests."""
    return {
        "install_jq": {
            "image": bundle.base_image,
            "features": {
                bundle.feature_id: {
                    "packages": "jq",
                    "strict": True,
                }
            },
        },
        "install_jq_ripgrep": {
            "image": bundle.base_image,
            "features": {
                bundle.feature_id: {
                    "packages": "jq,ripgrep",
                    "strict": True,
                }
            },
        },
        "install_jq_exact_version": {
            "image": bundle.base_image,
            "features": {
                bundle.feature_id: {
                    "packages": f"jq={jq_version}",
                    "strict": True,
                }
            },
        },
    }


if __name__ == "__main__":
    app()
