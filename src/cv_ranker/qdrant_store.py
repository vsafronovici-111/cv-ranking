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
    """Stores/looks up CV text-chunk embeddings in Qdrant.

    Each CV is split into a few chunks (summary/technologies/experience, see
    `cv_ranker.cv_structurer`), each stored as its own point so they can be
    matched independently; every point's payload carries the Postgres
    `cvs.id` (`cv_id`), `cv_file_name`, and `chunk_type` so results can be
    grouped back to the CV they came from. `ensure_collection` is idempotent
    and safe to call every time (mirrors `CVStore.init_schema()`).
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

    def upsert_cv_embedding(self, point_id: int | str, vector: list[float], payload: dict[str, Any]) -> None:
        """Store (or overwrite) the embedding for one CV chunk, at `point_id`.

        `point_id` must be unique per chunk (e.g. a UUID derived from
        `cv_id` + `chunk_type`) since one CV now owns multiple points; the
        CV itself is identified via `payload["cv_id"]`, not the point id.
        """
        try:
            self._client.upsert(
                collection_name=self.collection_name,
                points=[qmodels.PointStruct(id=point_id, vector=vector, payload=payload)],
            )
        except Exception as exc:
            raise CVVectorStoreError(f"Cannot upsert embedding for point_id={point_id}: {exc}") from exc

    def search_similar(self, vector: list[float], top_k: int = 10) -> list[dict[str, Any]]:
        """Return the `top_k` CVs whose stored embedding is closest to `vector`.

        Each result is `{"score": float, "payload": {...}}`, where `payload`
        carries whatever was stored by `upsert_cv_embedding`
        (`cv_id`, `cv_file_name`, `chunk_type`).
        """
        try:
            result = self._client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=top_k,
            )
        except Exception as exc:
            raise CVVectorStoreError(f"Cannot search Qdrant collection '{self.collection_name}': {exc}") from exc

        return [{"score": point.score, "payload": point.payload or {}} for point in result.points]
