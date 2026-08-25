"""Generate the deterministic build manifest bundled into frozen executables.

A frozen Pearipherals build must be able to name the exact source revision it
was produced from, independently of Authenticode (signing rewrites executable
bytes, so an artifact hash cannot serve as a stable build identity).

The manifest is intentionally tiny and whitelist-only: a prefixed revision
identity, the validated product version, and a fixed channel label. It carries
no local path, build directory, runner name, or user identifier, so it stays
safe to display in About / status and to include in a diagnostic report.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

# The same validated version grammar the PE version resource accepts, so the
# manifest and the Windows resource can never disagree about the product
# version: both are generated from one validated input.
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$")
REVISION_RE = re.compile(r"^[0-9a-fA-F]{40}$")
FROZEN_BUILD_ID_PREFIX = "git:"
BUILD_CHANNEL = "unsigned-source-build"
UNKNOWN_REVISION = "0" * 40


def validate_version(value) -> str:
    """Accept only a version the Windows version resource would also accept."""
    if not isinstance(value, str):
        raise ValueError("version must be a string")
    match = VERSION_RE.fullmatch(value.strip().removeprefix("v"))
    if not match:
        raise ValueError("version must be v?MAJOR.MINOR.PATCH[.BUILD]")
    parts = [int(part or 0) for part in match.groups()]
    if any(part > 65535 for part in parts):
        raise ValueError("Windows version components must be between 0 and 65535")
    return ".".join(str(part) for part in parts[:3])


def validate_revision(value) -> str:
    """Accept only a complete 40-hex Git revision, normalized to lowercase."""
    if not isinstance(value, str) or not REVISION_RE.fullmatch(value.strip()):
        raise ValueError("revision must be a complete 40-character hex Git SHA")
    return value.strip().lower()


def resolve_local_revision(repository) -> str:
    """Return HEAD only for a clean Git worktree; otherwise return unknown."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if status.returncode != 0 or status.stdout.strip():
            return UNKNOWN_REVISION
        revision = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if revision.returncode != 0:
            return UNKNOWN_REVISION
        return validate_revision(revision.stdout.strip())
    except Exception:
        return UNKNOWN_REVISION


def build_manifest(version, revision) -> dict:
    """Return the whitelist-only manifest, failing closed on any bad input."""
    return {
        "build_id": f"{FROZEN_BUILD_ID_PREFIX}{validate_revision(revision)}",
        "version": validate_version(version),
        "channel": BUILD_CHANNEL,
    }


def render(version, revision) -> str:
    """Render the manifest deterministically: sorted keys, fixed separators."""
    return json.dumps(
        build_manifest(version, revision),
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolve-local-revision", metavar="REPOSITORY")
    parser.add_argument("version", nargs="?")
    parser.add_argument("revision", nargs="?")
    parser.add_argument("output", nargs="?", type=Path)
    args = parser.parse_args()
    if args.resolve_local_revision is not None:
        if any(value is not None for value in (args.version, args.revision, args.output)):
            parser.error("--resolve-local-revision cannot be combined with manifest inputs")
        print(resolve_local_revision(Path(args.resolve_local_revision)))
        return 0
    if args.version is None or args.revision is None or args.output is None:
        parser.error("version, revision, and output are required")
    # Render before touching the filesystem so an invalid input leaves no file.
    content = render(args.version, args.revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
