"""Embedder seam (docs/12 §4). Fake (deterministic) for tests; OpenAI for prod."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dim(self) -> int: ...


class HashEmbedder:
    """Deterministic pseudo-embedding (tests + offline dev).

    Maps each token into a fixed 64-dim vector space so cosine similarity is
    meaningful for keyword overlaps without a real embedding model.
    """

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], "big") % self._dim
            vec[idx] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def _tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9_]+", text.lower())


class OpenAIEmbedder:
    """text-embedding-3-small via the OpenAI SDK (docs/12 §4)."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    @property
    def dim(self) -> int:
        return 1536

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text)
        return [float(x) for x in resp.data[0].embedding]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [[float(x) for x in d.embedding] for d in resp.data]


def build_embedder(*, provider: str = "hash", api_key: str = "") -> Any:
    if provider == "hash" or not api_key:
        return HashEmbedder()
    return OpenAIEmbedder(api_key=api_key)
