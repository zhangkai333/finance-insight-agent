from __future__ import annotations

import hashlib
import math
import struct
from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, text: str) -> list[float]: ...

    def serialize(self, text: str) -> bytes: ...


class HashingEmbedding:
    """无需外部模型的中文字符 n-gram 向量基线，可替换为 BGE/OpenAI-compatible provider。"""

    name = "char-ngram-hashing-v1"

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        compact = "".join(text.lower().split())
        vector = [0.0] * self.dimension
        grams = []
        for size in (1, 2, 3):
            grams.extend(compact[index:index + size] for index in range(max(0, len(compact) - size + 1)))
        for gram in grams:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little")
            index = value % self.dimension
            sign = 1.0 if (value >> 8) & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def serialize(self, text: str) -> bytes:
        values = self.embed(text)
        return struct.pack(f"{len(values)}f", *values)
