from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


class CVVectorStoreError(RuntimeError):
    pass


@dataclass
class QdrantSettings:
    url: str
    api_key: str = ""


class CVVectorStore:
    """Stores/looks up CV text embeddings in Qdrant.

    One point per CV, keyed by the Postgres `cvs.id` so it stays in lockstep
    with the row that owns the raw file data. `ensure_collection` is
    idempotent and safe to call every time (mirrors `CVStore.init_schema()`).
    """

    def __init__(self, settings: QdrantSettings, collection_name: str = "cv_embeddings"):
        try:
            self._client = QdrantClient(url=settings.url, api_key=settings.api_key or None)
        except Exception as exc:  # pragma: no cover - defensive: bad URL, etc.
            raise CVVectorStoreError(f"Cannot create Qdrant client for {settings.url}: {exc}") from exc

        self.collection_name = collection_name

    def ensure_collection(self, vector_size: int) -> None:
        """Create the collection if it doesn't exist yet."""
        try:
            existing = {c.name for c in self._client.get_collections().collections}
            if self.collection_name in existing:
                return
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
            )
        except Exception as exc:
            raise CVVectorStoreError(f"Cannot ensure Qdrant collection '{self.collection_name}': {exc}") from exc

    def upsert_cv_embedding(self, cv_id: int, vector: list[float], payload: dict[str, Any]) -> None:
        """Store (or overwrite) the embedding for CV `cv_id`."""
        try:
            self._client.upsert(
                collection_name=self.collection_name,
                points=[qmodels.PointStruct(id=cv_id, vector=vector, payload=payload)],
            )
        except Exception as exc:
            raise CVVectorStoreError(f"Cannot upsert embedding for cv_id={cv_id}: {exc}") from exc

