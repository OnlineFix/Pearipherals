"""Version and exact build-identity helpers for Pearipherals."""

import hashlib
import re
from dataclasses import dataclass


APP_VERSION = "1.2.0"

# A build identity is always prefixed so the reader knows exactly what was
# measured. `git:` names the exact source revision a frozen build was produced
# from. `entry-sha256:` names ONLY the entry script's bytes — it is an
# entry-script identity, never a complete source-build identity.
FROZEN_BUILD_ID_PREFIX = "git:"
ENTRY_BUILD_ID_PREFIX = "entry-sha256:"
_BUILD_ID_PATTERN = re.compile(
    rf"(?:{re.escape(FROZEN_BUILD_ID_PREFIX)}[0-9a-f]{{40}}"
    rf"|{re.escape(ENTRY_BUILD_ID_PREFIX)}[0-9a-f]{{64}})"
)
_VERSION_COMPONENT = r"(?:0|[1-9][0-9]*)"
_VERSION_PATTERN = re.compile(
    rf"{_VERSION_COMPONENT}\.{_VERSION_COMPONENT}\.{_VERSION_COMPONENT}"
)


def is_valid_build_id(build_id):
    """Return True only for a complete, prefixed, lowercase-hex build identity."""
    return isinstance(build_id, str) and _BUILD_ID_PATTERN.fullmatch(build_id) is not None


def is_valid_version(version):
    """Return True only for a normalized Windows-compatible product version."""
    if not isinstance(version, str) or _VERSION_PATTERN.fullmatch(version) is None:
        return False
    return all(int(part) <= 65535 for part in version.split("."))


@dataclass(frozen=True)
class BuildIdentity:
    version: str
    build_id: str

    def __post_init__(self):
        if not is_valid_version(self.version):
            raise ValueError(
                "version must be normalized MAJOR.MINOR.PATCH with components "
                "between 0 and 65535"
            )
        if not is_valid_build_id(self.build_id):
            raise ValueError(
                "build_id must be 'git:<40 hex>' (frozen source revision) or "
                "'entry-sha256:<64 hex>' (entry-script identity)"
            )


def hash_file(path, chunk_size=1024 * 1024):
    """Return the complete SHA-256 of *path* without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def entry_source_build_id(path):
    """Return the ENTRY-SCRIPT identity for *path*.

    This measures the entry script's bytes only, so it is explicitly
    not a complete source-build identity: imported modules, data files,
    and the interpreter are not covered by it.
    """
    return f"{ENTRY_BUILD_ID_PREFIX}{hash_file(path)}"
