"""Generate deterministic Windows version metadata for the frozen executable."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$")


def normalize_version(value: str) -> tuple[int, int, int, int]:
    match = VERSION_RE.fullmatch(value.strip().removeprefix("v"))
    if not match:
        raise ValueError("version must be v?MAJOR.MINOR.PATCH[.BUILD]")
    parts = [int(part or 0) for part in match.groups()]
    if any(part > 65535 for part in parts):
        raise ValueError("Windows version components must be between 0 and 65535")
    return tuple(parts)  # type: ignore[return-value]


def render(version: tuple[int, int, int, int]) -> str:
    numeric = ", ".join(map(str, version))
    display = ".".join(map(str, version[:3]))
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({numeric}),
    prodvers=({numeric}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Pearipherals open-source project'),
         StringStruct('FileDescription', 'Pearipherals for Apple input devices on Windows'),
         StringStruct('FileVersion', '{display}'),
         StringStruct('InternalName', 'Pearipherals'),
         StringStruct('LegalCopyright', 'Copyright Pearipherals contributors; MIT License'),
         StringStruct('OriginalFilename', 'Pearipherals.exe'),
         StringStruct('ProductName', 'Pearipherals'),
         StringStruct('ProductVersion', '{display}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(normalize_version(args.version)), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
