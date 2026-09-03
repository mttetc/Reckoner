"""Embeddings behind a tiny protocol.

- ``FastEmbedEmbedder``: local ONNX model (BAAI/bge-small-en-v1.5, 384 dims) via ``fastembed``.
  No external API, nothing leaves the machine. Default when the package is installed.
- ``HashEmbedder``: deterministic hashed bag-of-words projection, 384 dims, no dependencies.
  Used by tests/CI so retrieval *filtering* is verified without downloading a model. Ranking
  quality is irrelevant to what those tests assert. Never a source of displayed numbers.

Dimension is fixed (384) so both fit the same pgvector column; the embedder name is stored on
every chunk so mixed corpora can be detected and re-embedded.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.config import settings

DIMS = 384
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    name = "hash-bow-384"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * DIMS
            for tok in _TOKEN.findall(text.lower()):
                h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % DIMS
                sign = 1.0 if h[4] & 1 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


class FastEmbedEmbedder:
    name = "fastembed:BAAI/bge-small-en-v1.5"

    def __init__(self) -> None:
        from fastembed import TextEmbedding  # optional dependency (extra: rag)

        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._model.embed(texts)]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        if settings.embedder == "hash":
            _embedder = HashEmbedder()
        else:
            try:
                _embedder = FastEmbedEmbedder()
            except ImportError:
                _embedder = HashEmbedder()
    return _embedder


def reset_embedder() -> None:
    global _embedder
    _embedder = None
