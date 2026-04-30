# Offline Apt Feature Notes

This POC bundles flat, architecture-specific Debian trixie apt repositories
inside one Dev Container Feature payload. The install script selects
`repo/debian/trixie/<arch>` based on `dpkg --print-architecture`.

The dependency closure is resolved relative to `debian:trixie-slim`. That is
intentional for the POC and keeps the workflow easy to inspect. Production
variants should make dependency closure strategy explicit per base image.

The local apt source uses `trusted=yes` because repository signing is out of
scope for the first proof of concept.
