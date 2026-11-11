"""Refuse PE certificate tables that cannot be included in a signed MSIX."""

import struct
import sys
from pathlib import Path


def validate(path):
    with path.open("rb") as source:
        header = source.read(4096)
    if header[:2] != b"MZ":
        return
    try:
        pe = struct.unpack_from("<I", header, 60)[0]
        if header[pe:pe + 4] != b"PE\0\0":
            raise ValueError("Invalid PE header")
        optional = pe + 24
        magic = struct.unpack_from("<H", header, optional)[0]
        if magic not in (0x10b, 0x20b):
            raise ValueError("Unknown PE optional header")
        directories = optional + (112 if magic == 0x20b else 96)
        offset, size = struct.unpack_from("<II", header, directories + 32)
    except struct.error as error:
        raise ValueError(f"Truncated PE header: {path}") from error
    if not offset and not size:
        return
    if not offset or size < 8 or offset % 8 or offset + size > path.stat().st_size:
        raise ValueError(f"Invalid PE certificate table: {path}")


def validate_tree(root):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".exe", ".dll", ".pyd"}:
            validate(path)


if __name__ == "__main__":
    validate_tree(Path(sys.argv[1]))
