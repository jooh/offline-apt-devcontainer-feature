"""Tests for Dev Container Feature OCI layout normalization."""

from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from offline_apt_feature.oci_layout import normalize_devcontainer_feature_layout


class OciLayoutTests(unittest.TestCase):
    def test_normalize_devcontainer_feature_layout_rewrites_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layout = Path(tmp)
            blobs = layout / "blobs" / "sha256"
            blobs.mkdir(parents=True)
            (layout / "oci-layout").write_text(
                '{"imageLayoutVersion":"1.0.0"}',
                encoding="utf-8",
            )

            config_digest = _write_blob(blobs, b"{}")
            layer_digest = _write_blob(blobs, b"feature archive")
            manifest = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "annotations": {
                    "dev.containers.metadata": '{"id":"offline-apt","version":"1.0.0"}'
                },
                "config": {
                    "mediaType": "application/vnd.oci.empty.v1+json",
                    "digest": f"sha256:{config_digest}",
                    "size": 2,
                },
                "layers": [
                    {
                        "mediaType": "application/vnd.devcontainers.layer.v1+tar+gzip",
                        "digest": f"sha256:{layer_digest}",
                        "size": len(b"feature archive"),
                    }
                ],
            }
            manifest_digest = _write_blob(
                blobs,
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
            )
            _write_json(
                layout / "index.json",
                {
                    "schemaVersion": 2,
                    "manifests": [
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": f"sha256:{manifest_digest}",
                            "size": 10,
                            "annotations": {"org.opencontainers.image.ref.name": "1.0.0"},
                        },
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": f"sha256:{manifest_digest}",
                            "size": 10,
                            "annotations": {"org.opencontainers.image.ref.name": "latest"},
                        },
                    ],
                },
            )

            results = normalize_devcontainer_feature_layout(layout, feature_id="offline-apt")

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].changed)
            self.assertNotEqual(results[0].old_digest, results[0].new_digest)

            index = _read_json(layout / "index.json")
            descriptors = index["manifests"]
            self.assertEqual(descriptors[0]["digest"], descriptors[1]["digest"])
            self.assertEqual(descriptors[0]["size"], descriptors[1]["size"])

            normalized_digest = descriptors[0]["digest"].removeprefix("sha256:")
            normalized = _read_json(blobs / normalized_digest)
            self.assertEqual(
                normalized["config"]["mediaType"],
                "application/vnd.devcontainers",
            )
            self.assertEqual(
                normalized["layers"][0]["mediaType"],
                "application/vnd.devcontainers.layer.v1+tar",
            )
            self.assertEqual(
                normalized["layers"][0]["annotations"]["org.opencontainers.image.title"],
                "devcontainer-feature-offline-apt.tgz",
            )
            self.assertEqual(
                normalized["annotations"]["com.github.package.type"],
                "devcontainer_feature",
            )

            second_results = normalize_devcontainer_feature_layout(
                layout,
                feature_id="offline-apt",
            )
            self.assertEqual(len(second_results), 1)
            self.assertFalse(second_results[0].changed)


def _write_blob(blobs: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    (blobs / digest).write_bytes(data)
    return digest


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} did not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
