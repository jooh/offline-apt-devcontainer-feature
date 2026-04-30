"""Helpers for reading generated flat apt repository indexes."""

from dataclasses import dataclass
from pathlib import Path
import gzip


@dataclass(frozen=True)
class PackageRecord:
    """A package paragraph from a Debian Packages index."""

    package: str
    version: str
    architecture: str
    filename: str
    sha256: str
    size: int

    @property
    def deb_filename(self) -> str:
        """Return the local .deb basename from the index filename."""
        return Path(self.filename).name


def parse_packages_index(text: str) -> list[dict[str, str]]:
    """Parse Debian control paragraphs from a Packages index."""
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    current_key: str | None = None

    for line in text.splitlines():
        if not line:
            if current:
                records.append(current)
                current = {}
                current_key = None
            continue
        if line[0].isspace() and current_key is not None:
            current[current_key] = f"{current[current_key]}\n{line}"
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"invalid Packages line: {line}")
        current_key = key
        current[key] = value.strip()

    if current:
        records.append(current)
    return records


def read_packages_gz(path: Path) -> list[PackageRecord]:
    """Read Package records from a compressed apt Packages.gz file."""
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        raw_records = parse_packages_index(handle.read())

    records: list[PackageRecord] = []
    for raw in raw_records:
        records.append(
            PackageRecord(
                package=raw["Package"],
                version=raw["Version"],
                architecture=raw["Architecture"],
                filename=raw["Filename"],
                sha256=raw["SHA256"],
                size=int(raw["Size"]),
            )
        )
    return records


def deb_files(repo_dir: Path) -> list[Path]:
    """Return sorted .deb files from a flat repository directory."""
    return sorted(repo_dir.glob("*.deb"), key=lambda path: path.name)
