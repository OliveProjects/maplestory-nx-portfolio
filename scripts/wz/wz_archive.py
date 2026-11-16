"""
WZ archive reader — opens a .wz package and pulls out images by name.

Together with img_parser this removes the last reason to touch an external
tool: the bot can read any of the ~16 700 maps straight from the game files.

WHAT AN ARCHIVE ADDS OVER A STANDALONE .img

An exported .img is a property tree starting at byte 0. Inside an archive the
same tree sits at an offset that is deliberately obfuscated, and undoing that
needs a "version hash" which is not stored anywhere. Only an 8-bit checksum of
it is, so recovering it means brute-forcing every version 0..32767, keeping the
~140 whose checksum matches, and then trial-parsing the root directory with
each until one produces sane names and in-bounds offsets.

That sounds fragile and is not: a wrong hash produces garbage within a few
bytes, so validation is decisive.

FORMAT

  header:  "PKG1", int64 data size, int32 header size, copyright string,
           uint16 encrypted version

  directory entry:
      type 1  unknown          skip 10 bytes
      type 2  name at offset   int32 offset into the string pool, then a
                               second type byte (3 or 4) and the usual fields
      type 3  subdirectory     name, size, checksum, obfuscated offset
      type 4  image (.img)     same fields; the offset is where the property
                               tree begins

  offset deobfuscation, per entry position:
      x = (pos - header_size) ^ 0xFFFFFFFF
      x = x * version_hash
      x = x - 0x581C3F6D
      x = rotate_left(x, x & 0x1F)
      x = x ^ read_uint32()
      x = x + header_size * 2

STRINGS ARE NOT ENCRYPTED IN THIS CLIENT. Verified in img_parser: the plain
incrementing XOR mask alone decodes node names, so the AES WzKey is all zeros.
If a future patch changes that, directory names come out as mojibake and the
validator below will reject every candidate version, which is the failure mode
we want rather than silent garbage.
"""
from __future__ import annotations

import glob
import os
import struct
from typing import Optional

from .img_parser import WzImgParser


def _rotl(v: int, n: int) -> int:
    n &= 0x1F
    return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF


class WzEntry:
    __slots__ = ("name", "kind", "size", "checksum", "offset", "children", "archive")

    def __init__(self, name, kind, size, checksum, offset, archive):
        self.name = name
        self.kind = kind                  # "dir" or "img"
        self.size = size
        self.checksum = checksum
        self.offset = offset
        self.archive = archive
        self.children: dict[str, "WzEntry"] = {}

    def parse(self) -> dict:
        """Parse this image's property tree."""
        if self.kind != "img":
            raise ValueError("%s is a directory, not an image" % self.name)
        blob = self.archive.data[self.offset:self.offset + self.size]
        return WzImgParser(blob).parse()

    def __repr__(self):
        return "WzEntry(%r, %s, %d bytes)" % (self.name, self.kind, self.size)


class WzArchive:
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        self.header_size = 0
        self.version_hash = 0
        self.version = -1
        self.root: dict[str, WzEntry] = {}
        self._read_header()
        self._resolve_version()

    # ── header ───────────────────────────────────────────────────────────

    def _read_header(self):
        if self.data[:4] != b"PKG1":
            raise ValueError("not a WZ package: %s" % self.path)
        self.data_size = struct.unpack_from("<Q", self.data, 4)[0]
        self.header_size = struct.unpack_from("<I", self.data, 12)[0]
        end = self.data.index(b"\x00", 16)
        self.copyright = self.data[16:end].decode("latin1")
        self.enc_version = struct.unpack_from("<H", self.data, self.header_size)[0]

    @staticmethod
    def _hash_for(version: int) -> tuple[int, int]:
        h = 0
        for c in str(version):
            h = (h * 32 + ord(c) + 1) & 0xFFFFFFFF
        chk = 0xFF ^ ((h >> 24) & 0xFF) ^ ((h >> 16) & 0xFF) \
                   ^ ((h >> 8) & 0xFF) ^ (h & 0xFF)
        return h, chk

    def _resolve_version(self):
        """Brute-force the version, then prove it by parsing the root."""
        for v in range(0, 32768):
            h, chk = self._hash_for(v)
            if chk != self.enc_version:
                continue
            try:
                root = self._read_directory(self.header_size + 2, h)
            except Exception:
                continue
            if self._looks_sane(root):
                self.version, self.version_hash, self.root = v, h, root
                return
        raise ValueError("could not resolve WZ version for %s" % self.path)

    def _looks_sane(self, root: dict) -> bool:
        """A wrong hash yields junk names and out-of-range offsets."""
        if not root:
            return False
        for e in root.values():
            if not e.name or len(e.name) > 64:
                return False
            if not all(32 <= ord(c) < 127 for c in e.name):
                return False
            if not (0 < e.offset < len(self.data)):
                return False
            if not (0 <= e.size <= len(self.data)):
                return False
        return True

    # ── directory ────────────────────────────────────────────────────────

    def _read_directory(self, pos: int, vhash: int) -> dict[str, WzEntry]:
        p = WzImgParser(self.data)
        p.p = pos
        out: dict[str, WzEntry] = {}
        for _ in range(p.compressed_int()):
            kind_byte = p.u8()
            name = ""
            if kind_byte == 1:
                p.p += 10
                continue
            if kind_byte == 2:
                # name lives elsewhere: int32 offset into the string pool,
                # where a fresh type byte precedes the name
                str_off = p.i32() + self.header_size + 1
                inner = WzImgParser(self.data)
                inner.p = str_off
                kind_byte = inner.u8()
                name = inner._string_at(inner.p)
            elif kind_byte in (3, 4):
                # NOTE: a directory entry stores the name as a bare
                # length-prefixed string. Unlike a property node there is no
                # 0x73/0x01 marker byte in front of it, so string() would
                # eat the length byte as a marker and derail everything after.
                name = p._string_at(p.p)
                p._skip_string_body()
            else:
                raise ValueError("bad directory entry type %d" % kind_byte)

            size = p.compressed_int()
            checksum = p.compressed_int()
            offset = self._deobfuscate_offset(p, vhash)
            out[name] = WzEntry(
                name, "dir" if kind_byte == 3 else "img",
                size, checksum, offset, self)
        # recurse into subdirectories now that offsets are known
        for e in out.values():
            if e.kind == "dir":
                e.children = self._read_directory(e.offset, vhash)
        return out

    def _deobfuscate_offset(self, p: WzImgParser, vhash: int) -> int:
        pos = p.p
        x = (pos - self.header_size) ^ 0xFFFFFFFF
        x = (x * vhash) & 0xFFFFFFFF
        x = (x - 0x581C3F6D) & 0xFFFFFFFF
        x = _rotl(x, x & 0x1F)
        x = (x ^ p.u32()) & 0xFFFFFFFF
        x = (x + self.header_size * 2) & 0xFFFFFFFF
        return x

    # ── lookup ───────────────────────────────────────────────────────────

    def find(self, *path: str) -> Optional[WzEntry]:
        """find('Map', 'Map1', '120010100.img') -> WzEntry or None."""
        node = self.root
        entry = None
        for part in path:
            entry = node.get(part)
            if entry is None:
                return None
            node = entry.children
        return entry

    def walk(self, entries: dict | None = None, prefix: str = ""):
        """Yield (path, entry) for every node."""
        for name, e in (entries if entries is not None else self.root).items():
            full = prefix + "/" + name if prefix else name
            yield full, e
            if e.children:
                yield from self.walk(e.children, full)


def open_map(data_root: str, map_id: str) -> dict:
    """Load one map's property tree straight from the game files.

    data_root points at the client's Data folder, e.g.
    D:/Spel/Maplestory/appdata/Data
    """
    mid = str(map_id).zfill(9)
    bucket = "Map" + mid[0]
    folder = os.path.join(data_root, "Map", "Map", bucket)
    # A bucket can be split over several parts (Map9 has _000 and _001), and
    # which part holds a given map is not derivable from the id, so scan them.
    parts = sorted(glob.glob(os.path.join(folder, bucket + "_[0-9][0-9][0-9].wz")))
    if not parts:
        raise FileNotFoundError("no archives in %s" % folder)
    for archive in parts:
        arc = WzArchive(archive)
        entry = arc.root.get(mid + ".img")
        if entry is None:
            for _path, e in arc.walk():
                if e.kind == "img" and e.name == mid + ".img":
                    entry = e
                    break
        if entry is not None:
            return entry.parse()
    raise KeyError("map %s not found in %s" % (map_id, folder))
