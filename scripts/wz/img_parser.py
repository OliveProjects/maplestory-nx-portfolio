"""
WZ image (.img) parser — pure Python, no dependencies, no AES.

Parses a standalone .img node exported from a WZ archive (e.g. by
WzComparerR2) into a plain nested dict. This is the bot's source of GROUND
TRUTH for map geometry, replacing the foothold/rope/portal data that used to
be inferred from pixels.

WHY THIS IS EASY, AND WHY WE THOUGHT IT WASN'T

The project spent weeks believing the client used a "modern split WZ format"
that would need a rewrite. It does not. Every .wz here is classic PKG1, and
this client stores strings with the plain incrementing XOR mask only: the AES
WzKey is all zeros. Verified by decoding the first node name with nothing but
the mask, which yields exactly "Property".

A standalone .img is easier still than the archive it came from. Inside an
archive, every offset is obfuscated by a version hash that has to be
brute-forced. An exported .img has none of that: it is a self-contained
property tree starting at byte 0.

FORMAT

  "Property", uint16 reserved, compressed-int count, then entries of:
      name: string       type: byte
      0x00        null
      0x02, 0x0B  int16
      0x03, 0x13  compressed int32
      0x04, 0x14  float32   (0x80 prefix means a real value follows, else 0.0)
      0x05        float64
      0x08        string
      0x09        extended: uint32 block length, then a typed object

  Extended objects we care about:
      "Property"          nested sub-properties
      "Shape2D#Vector2D"  two compressed ints (x, y)      <- foothold points
      "Canvas", "UOL", "Sound_DX8"  skipped by block length

Strings appear twice over: a marker byte selects inline (0x00/0x73) or a
back-reference to an earlier string by absolute offset (0x01/0x1B). The
back-reference is why the file has so few readable bytes: every repeated key
like "x" or "y" is stored once and pointed at thereafter.
"""
from __future__ import annotations

import struct
import zlib
from typing import Any


class WzImgParser:
    def __init__(self, data: bytes):
        self.d = data
        self.p = 0

    # ── primitives ───────────────────────────────────────────────────────

    def u8(self) -> int:
        v = self.d[self.p]; self.p += 1
        return v

    def i8(self) -> int:
        v = struct.unpack_from("<b", self.d, self.p)[0]; self.p += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.d, self.p)[0]; self.p += 2
        return v

    def i16(self) -> int:
        v = struct.unpack_from("<h", self.d, self.p)[0]; self.p += 2
        return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.p)[0]; self.p += 4
        return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.p)[0]; self.p += 4
        return v

    def f32(self) -> float:
        v = struct.unpack_from("<f", self.d, self.p)[0]; self.p += 4
        return v

    def f64(self) -> float:
        v = struct.unpack_from("<d", self.d, self.p)[0]; self.p += 8
        return v

    def compressed_int(self) -> int:
        """One signed byte, or a full int32 when that byte is -128."""
        b = self.i8()
        return self.i32() if b == -128 else b

    def compressed_float(self) -> float:
        b = self.i8()
        return self.f32() if b == -128 else float(b)

    def compressed_long(self) -> int:
        """One signed byte, or a full int64 when that byte is -128."""
        b = self.i8()
        if b != -128:
            return b
        v = struct.unpack_from("<q", self.d, self.p)[0]; self.p += 8
        return v

    # ── strings ──────────────────────────────────────────────────────────

    def _string_at(self, pos: int) -> str:
        """Read a length-prefixed, mask-encrypted string at an absolute pos."""
        save, self.p = self.p, pos
        try:
            n = self.i8()
            if n == 0:
                return ""
            if n < 0:                                   # ASCII
                count = self.i32() if n == -128 else -n
                raw = self.d[self.p:self.p + count]; self.p += count
                mask = 0xAA
                out = bytearray(count)
                for i, b in enumerate(raw):
                    out[i] = b ^ (mask & 0xFF); mask += 1
                return out.decode("latin1")
            # UTF-16LE
            count = self.i32() if n == 127 else n
            out = []
            mask = 0xAAAA
            for _ in range(count):
                c = self.u16() ^ (mask & 0xFFFF); mask += 1
                out.append(chr(c))
            return "".join(out)
        finally:
            self.p = save

    def string(self) -> str:
        """A string field: either inline here, or an offset to one elsewhere."""
        t = self.u8()
        if t in (0x00, 0x73):
            s = self._string_at(self.p)
            self._skip_string_body()
            return s
        if t in (0x01, 0x1B):
            return self._string_at(self.u32())
        raise ValueError("unknown string marker 0x%02X at %d" % (t, self.p - 1))

    def _skip_string_body(self):
        n = self.i8()
        if n == 0:
            return
        if n < 0:
            count = self.i32() if n == -128 else -n
            self.p += count
        else:
            count = self.i32() if n == 127 else n
            self.p += count * 2

    # ── property tree ────────────────────────────────────────────────────

    def parse(self) -> dict:
        """Parse the whole image. Returns the root property dict."""
        root_type = self.string()
        if root_type != "Property":
            raise ValueError("expected 'Property' at root, got %r" % root_type)
        return self._properties()

    def _properties(self) -> dict:
        self.u16()                                      # reserved, always 0
        out: dict[str, Any] = {}
        for _ in range(self.compressed_int()):
            name = self.string()
            out[name] = self._value()
        return out

    def _value(self) -> Any:
        t = self.u8()
        if t == 0x00:
            return None
        if t in (0x02, 0x0B):
            return self.i16()
        if t in (0x03, 0x13):
            return self.compressed_int()
        if t == 0x04:
            return self.compressed_float()
        # 0x14 är ett komprimerat int64, inte ett flyttal. Lästes den som
        # float hamnade parsern ur takt på objekten i Map/Obj (2026-10-25).
        if t == 0x14:
            return self.compressed_long()
        if t == 0x05:
            return self.f64()
        if t == 0x08:
            return self.string()
        if t == 0x09:
            end = self.u32() + self.p
            v = self._extended(end)
            self.p = end                                # trust the block length
            return v
        raise ValueError("unknown value type 0x%02X at %d" % (t, self.p - 1))

    def _extended(self, end: int) -> Any:
        kind = self.string()
        if kind == "Property":
            return self._properties()
        # Convex2D är en lista utan namn: ett antal, sedan lika många
        # utökade värden (oftast Vector2D). Lästes den som Property kom
        # parsern ur takt på objekten i Map/Obj (2026-10-25).
        if kind == "Shape2D#Convex2D":
            return [self._extended(end) for _ in range(self.compressed_int())]
        if kind == "Shape2D#Vector2D":
            return {"x": self.compressed_int(), "y": self.compressed_int()}
        if kind == "Canvas":
            return self._canvas(end)
        # UOL / Sound_DX8 / anything else: the caller restores self.p from the
        # block length regardless.
        return {"_type": kind}

    # ── canvas ───────────────────────────────────────────────────────────

    def _canvas(self, end: int) -> dict:
        """Read a sprite: dimensions, format, and the compressed pixels.

        Layout, decoded by hand from real nodes because the field order differs
        between clients and guessing it wastes an afternoon:

            byte      unknown, 0 here
            byte      hasProperty flag           <- the one most write-ups omit
            if hasProperty == 1:
                uint16    reserved, always 0
                cint      property count, then that many name/value pairs
            cint      width
            cint      height
            cint      format
            byte      format2, a scale exponent
            int32     unknown
            int32     data length
            byte      unknown
            bytes     zlib stream (0x78 0x9C)

        Verified on 1210102.img (Orange Mushroom): 63x58, format 1, 2125 bytes
        compressed against 7308 for BGRA4444 uncompressed.

        ⚠️ THE FLAG IS WHY EVERY MAP'S miniMap READ BACK AS 0x0. The mob sprite
        this was first decoded against has hasProperty == 0, so reading width
        straight after the two bytes happened to work. A map's miniMap canvas
        has hasProperty == 1 carrying an `_outlink`, so the property block was
        being eaten as width/height and every map reported a 0x0 minimap with
        0 bytes of pixels. The panel size then had to be guessed from
        `miniMap/width / mag`, a rule that is right on some maps and 2x wrong
        on others. Skipping the block correctly makes the real size readable.

        The pixels are NOT decoded here. This returns the raw block so the
        caller can decide, because a mob image has eight frames and inflating
        all of them on every map load would cost far more than it is worth.
        Use `decode_canvas()` when the pixels are actually wanted.
        """
        self.u8()
        has_property = self.u8()
        props: dict[str, Any] = {}
        if has_property == 1:
            props = self._properties()
        w = self.compressed_int()
        h = self.compressed_int()
        fmt = self.compressed_int()
        fmt2 = self.u8()
        self.i32()
        length = self.i32()
        self.u8()
        data = bytes(self.d[self.p:min(end, self.p + max(0, length - 1))])
        node = {"_type": "Canvas", "width": w, "height": h,
                "format": fmt, "scale": fmt2, "data": data}
        if props:
            node["properties"] = props
            # An outlinked canvas stores its pixels in another image; the path
            # is relative to the WZ root, e.g. "Map/MapHelper.img/minimap/...".
            link = props.get("_outlink") or props.get("_inlink")
            if isinstance(link, str):
                node["link"] = link
        return node


def decode_canvas(node: dict):
    """Inflate a Canvas node into an RGBA numpy array, or None.

    Kept out of the parser so a map load does not pay for pixels it will never
    look at: one mob image holds eight frames and a map holds many mobs.

    Formats seen in this client are BGRA4444 (1) and BGRA8888 (2). The 4-bit
    channels are widened by repeating the nibble, so 0xF becomes 0xFF rather
    than 0xF0, which keeps white white instead of dimming everything by 6%.

    `scale` is a downscale exponent: the stored image is (w >> scale) wide and
    has to be blown back up. Zero on every sprite checked so far, handled
    anyway because a silent half-size sprite would be a miserable bug to find.
    """
    import numpy as np

    if not node or node.get("_type") != "Canvas" or not node.get("data"):
        return None
    w, h = node["width"], node["height"]
    scale = node.get("scale", 0) or 0
    sw, sh = max(1, w >> scale), max(1, h >> scale)
    # decompressobj rather than decompress: the block boundary clips the
    # stream's trailing adler32, so a strict inflate raises "incomplete or
    # truncated" even though every pixel byte is present. Measured on a 63x55
    # sprite: the partial inflate yields exactly 6930 bytes, which is exactly
    # 63 * 55 * 2. Taking what it produced is correct here, and the size check
    # below is what actually guards against a genuinely short stream.
    try:
        raw = zlib.decompressobj().decompress(node["data"])
    except zlib.error:
        return None

    fmt = node["format"]
    if fmt == 1:                                    # BGRA4444
        need = sw * sh * 2
        if len(raw) < need:
            return None
        a = np.frombuffer(raw[:need], dtype=np.uint8).reshape(sh, sw, 2)
        lo, hi = a[:, :, 0], a[:, :, 1]
        out = np.empty((sh, sw, 4), np.uint8)
        out[:, :, 2] = (lo & 0x0F) | ((lo & 0x0F) << 4)      # B
        out[:, :, 1] = (lo & 0xF0) | ((lo & 0xF0) >> 4)      # G
        out[:, :, 0] = (hi & 0x0F) | ((hi & 0x0F) << 4)      # R
        out[:, :, 3] = (hi & 0xF0) | ((hi & 0xF0) >> 4)      # A
    elif fmt == 2:                                  # BGRA8888
        need = sw * sh * 4
        if len(raw) < need:
            return None
        a = np.frombuffer(raw[:need], dtype=np.uint8).reshape(sh, sw, 4)
        out = a[:, :, [2, 1, 0, 3]].copy()
    else:
        return None

    if scale:
        out = np.repeat(np.repeat(out, 1 << scale, axis=0), 1 << scale, axis=1)
        out = out[:h, :w]
    return out


def parse_img(path: str) -> dict:
    with open(path, "rb") as f:
        return WzImgParser(f.read()).parse()
