"""OCI layout helpers for Dev Container Feature publishing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
from typing import Any


DEVCONTAINERS_CONFIG_MEDIA_TYPE = "application/vnd.devcontainers"
DEVCONTAINERS_LAYER_MEDIA_TYPE = "application/vnd.devcontainers.layer.v1+tar"
DEVCONTAINERS_PACKAGE_TYPE = "devcontainer_feature"


@dataclass(frozen=True)
class NormalizedManifest:
    """A manifest descriptor rewritten in an OCI layout."""

    old_digest: str
    new_digest: str
    size: int
    changed: bool


def normalize_devcontainer_feature_layout(
    layout: Path,
    *,
    feature_id: str | None = None,
) -> list[NormalizedManifest]:
    """Normalize devcontainer-rs OCI output for the official Dev Containers CLI.

    devcontainer-rs currently writes Feature artifacts with the empty OCI config
    media type. The official CLI expects the same empty config bytes to be
    labeled as a Dev Containers config, and rejects the artifact otherwise.
    """
    index_path = layout / "index.json"
    blobs_dir = layout / "blobs" / "sha256"
    if not index_path.is_file():
        raise FileNotFoundError(f"missing OCI index: {index_path}")
    if not blobs_dir.is_dir():
        raise FileNotFoundError(f"missing OCI blobs directory: {blobs_dir}")

    index = _read_json(index_path)
    manifests = index.get("manifests")
    if not isinstance(manifests, list) or not manifests:
        raise ValueError(f"{index_path} has no manifests")

    rewritten: dict[str, NormalizedManifest] = {}
    for descriptor in manifests:
        if not isinstance(descriptor, dict):
            raise ValueError(f"{index_path} contains a non-object manifest descriptor")
        digest = descriptor.get("digest")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ValueError(f"{index_path} contains an invalid digest: {digest!r}")
        old_digest = digest.removeprefix("sha256:")
        if old_digest not in rewritten:
            rewritten[old_digest] = _normalize_manifest_blob(
                blobs_dir,
                old_digest,
                feature_id=feature_id,
            )
        result = rewritten[old_digest]
        descriptor["digest"] = f"sha256:{result.new_digest}"
        descriptor["size"] = result.size

    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return list(rewritten.values())


def _normalize_manifest_blob(
    blobs_dir: Path,
    old_digest: str,
    *,
    feature_id: str | None,
) -> NormalizedManifest:
    manifest_path = blobs_dir / old_digest
    manifest = _read_json(manifest_path)
    changed = _normalize_manifest(manifest, feature_id=feature_id)
    data = _canonical_json_bytes(manifest)
    new_digest = hashlib.sha256(data).hexdigest()
    new_path = blobs_dir / new_digest
    if changed or new_digest != old_digest:
        new_path.write_bytes(data)
    return NormalizedManifest(
        old_digest=old_digest,
        new_digest=new_digest,
        size=len(data),
        changed=changed or new_digest != old_digest,
    )


def _normalize_manifest(manifest: dict[str, Any], *, feature_id: str | None) -> bool:
    changed = False

    config = manifest.get("config")
    if not isinstance(config, dict):
        raise ValueError("OCI manifest has no config object")
    if config.get("mediaType") != DEVCONTAINERS_CONFIG_MEDIA_TYPE:
        config["mediaType"] = DEVCONTAINERS_CONFIG_MEDIA_TYPE
        changed = True

    annotations = manifest.setdefault("annotations", {})
    if not isinstance(annotations, dict):
        raise ValueError("OCI manifest annotations must be an object")
    if annotations.get("com.github.package.type") != DEVCONTAINERS_PACKAGE_TYPE:
        annotations["com.github.package.type"] = DEVCONTAINERS_PACKAGE_TYPE
        changed = True

    layers = manifest.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("OCI manifest has no layers")
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError("OCI manifest contains a non-object layer")
        if layer.get("mediaType") != DEVCONTAINERS_LAYER_MEDIA_TYPE:
            layer["mediaType"] = DEVCONTAINERS_LAYER_MEDIA_TYPE
            changed = True
        if feature_id is not None:
            layer_annotations = layer.setdefault("annotations", {})
            if not isinstance(layer_annotations, dict):
                raise ValueError("OCI layer annotations must be an object")
            title = f"devcontainer-feature-{feature_id}.tgz"
            if layer_annotations.get("org.opencontainers.image.title") != title:
                layer_annotations["org.opencontainers.image.title"] = title
                changed = True

    return changed


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
