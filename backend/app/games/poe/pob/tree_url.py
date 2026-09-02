"""Decode pathofexile.com passive tree URLs (used by old PoB exports that lack ``nodes=``).

Binary layout (big-endian) after base64url decoding:
  version u32 · class u8 · ascendancy u8 · then version-dependent header · node ids u16[]
Versions 4 and 5 are fully supported; version ≥ 6 adds a mastery section that is also handled.
Anything unrecognised returns ``None``: an unknown tree is a valid result, a guessed one is not.
"""

from __future__ import annotations

import base64
import binascii
import struct
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True)
class DecodedTree:
    version: int
    class_id: int
    ascendancy_id: int
    node_ids: tuple[int, ...]
    mastery_effects: dict[int, int] = field(default_factory=dict)


def decode_tree_url(url: str) -> DecodedTree | None:
    path = urlparse(url.strip()).path.rstrip("/")
    token = path.rsplit("/", 1)[-1]
    if not token:
        return None
    try:
        data = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (binascii.Error, ValueError):
        return None
    if len(data) < 6:
        return None
    version, class_id, asc_id = struct.unpack(">IBB", data[:6])
    pos = 6
    try:
        if version <= 3:
            return None
        if version in (4, 5):
            pos += 1  # fullscreen flag
            count = (len(data) - pos) // 2
            nodes = struct.unpack(f">{count}H", data[pos : pos + 2 * count])
            return DecodedTree(version, class_id, asc_id, tuple(nodes))
        # version 6: node count u8, nodes, cluster count u8, cluster nodes, mastery count u8, pairs
        n = data[pos]
        pos += 1
        nodes = struct.unpack(f">{n}H", data[pos : pos + 2 * n])
        pos += 2 * n
        c = data[pos]
        pos += 1
        cluster = struct.unpack(f">{c}H", data[pos : pos + 2 * c])
        pos += 2 * c
        masteries: dict[int, int] = {}
        if pos < len(data):
            m = data[pos]
            pos += 1
            pairs = struct.unpack(f">{2 * m}H", data[pos : pos + 4 * m])
            masteries = {pairs[i + 1]: pairs[i] for i in range(0, len(pairs), 2)}
        return DecodedTree(version, class_id, asc_id, tuple(nodes) + tuple(cluster), masteries)
    except (struct.error, IndexError):
        return None
