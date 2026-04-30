"""Validated bundle configuration models."""

from pathlib import Path
import re

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$")
SUPPORTED_ARCHITECTURES = {"amd64", "arm64"}


class PackageRequest(BaseModel):
    """A top-level Debian package requested for the bundled repository."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate that a package name uses conservative Debian syntax."""
        if not PACKAGE_NAME_RE.fullmatch(value):
            raise ValueError(f"invalid Debian package name: {value}")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str | None) -> str | None:
        """Validate that an optional package version is shell-safe."""
        if value is not None and not VERSION_RE.fullmatch(value):
            raise ValueError(f"invalid Debian package version: {value}")
        return value

    def spec(self) -> str:
        """Render the apt package spec for resolution or installation."""
        if self.version is None:
            return self.name
        return f"{self.name}={self.version}"


class Bundle(BaseModel):
    """The complete offline apt Feature bundle configuration."""

    model_config = ConfigDict(extra="forbid")

    distro: str
    codename: str
    base_image: str
    feature_id: str
    tag: str
    architectures: list[str] = Field(min_length=1)
    packages: list[PackageRequest] = Field(min_length=1)

    @field_validator("distro")
    @classmethod
    def validate_distro(cls, value: str) -> str:
        """Restrict the POC to Debian."""
        if value != "debian":
            raise ValueError('only distro "debian" is supported')
        return value

    @field_validator("codename")
    @classmethod
    def validate_codename(cls, value: str) -> str:
        """Restrict the POC to Debian trixie."""
        if value != "trixie":
            raise ValueError('only codename "trixie" is supported')
        return value

    @field_validator("feature_id")
    @classmethod
    def validate_feature_id(cls, value: str) -> str:
        """Validate that the Feature id is safe for paths and OCI refs."""
        if not PACKAGE_NAME_RE.fullmatch(value):
            raise ValueError(f"invalid Feature id: {value}")
        return value

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str) -> str:
        """Validate that the OCI tag is conservative and non-empty."""
        if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", value):
            raise ValueError(f"invalid OCI tag: {value}")
        return value

    @field_validator("architectures")
    @classmethod
    def validate_architectures(cls, value: list[str]) -> list[str]:
        """Validate that only amd64 and arm64 architectures are requested."""
        seen: set[str] = set()
        for arch in value:
            if arch not in SUPPORTED_ARCHITECTURES:
                raise ValueError(f"unsupported architecture: {arch}")
            if arch in seen:
                raise ValueError(f"duplicate architecture: {arch}")
            seen.add(arch)
        return value

    @model_validator(mode="after")
    def validate_package_conflicts(self) -> "Bundle":
        """Reject duplicate package names with conflicting versions."""
        seen: dict[str, str | None] = {}
        for package in self.packages:
            if package.name in seen and seen[package.name] != package.version:
                raise ValueError(
                    f"conflicting versions for package {package.name}: "
                    f"{seen[package.name]} and {package.version}"
                )
            seen[package.name] = package.version
        return self

    def top_level_specs(self) -> list[str]:
        """Return de-duplicated top-level apt package specs in bundle order."""
        seen: set[str] = set()
        specs: list[str] = []
        for package in self.packages:
            spec = package.spec()
            if package.name not in seen:
                specs.append(spec)
                seen.add(package.name)
        return specs

    def feature_dir(self, project_root: Path) -> Path:
        """Return the local Feature directory for this bundle."""
        return project_root / "src" / self.feature_id

    def repo_dir(self, project_root: Path, architecture: str) -> Path:
        """Return the generated flat apt repository directory for an architecture."""
        return (
            self.feature_dir(project_root)
            / "repo"
            / self.distro
            / self.codename
            / architecture
        )


def load_bundle(path: Path) -> Bundle:
    """Load and validate a bundle YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raise ValueError(f"empty bundle file: {path}")
    return Bundle.model_validate(raw)
