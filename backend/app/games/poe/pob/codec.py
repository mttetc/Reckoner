"""PoB import/export code ⇄ XML bytes.

A PoB code is ``base64url( zlib( xml ) )``. Padding is usually stripped; some paste services
wrap lines.
"""

from __future__ import annotations

import base64
import binascii
import zlib

from app.domain.errors import InvalidBuildCode

_MAX_DECOMPRESSED = 8 * 1024 * 1024  # 8 MiB — real exports are tens of KiB


def decode(code: str) -> bytes:
    compact = "".join(code.split())
    if not compact:
        raise InvalidBuildCode("empty build code")
    # PoB uses URL-safe base64 ('-' and '_'); tolerate standard alphabet too.
    compact = compact.replace("+", "-").replace("/", "_")
    padded = compact + "=" * (-len(compact) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError) as exc:
        raise InvalidBuildCode("not base64") from exc
    d = zlib.decompressobj()
    try:
        xml = d.decompress(raw, _MAX_DECOMPRESSED)
    except zlib.error as exc:
        raise InvalidBuildCode("not a zlib stream") from exc
    if d.unconsumed_tail:
        raise InvalidBuildCode("decompressed payload exceeds size limit")
    if not xml.lstrip().startswith(b"<"):
        raise InvalidBuildCode("decoded payload is not XML")
    return xml


def encode(xml: bytes) -> str:
    return base64.urlsafe_b64encode(zlib.compress(xml, 9)).decode().rstrip("=")


def looks_like_code(payload: str) -> bool:
    compact = "".join(payload.split())
    if len(compact) < 40:
        return False
    # zlib header bytes 0x78 0x9c / 0x78 0xda encode to 'eJ' / 'eN' in base64.
    return compact[:2] in {"eJ", "eN"} and all(c.isalnum() or c in "-_=+/" for c in compact)
