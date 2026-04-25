"""Chroma Cloud storage for Step 2 evidence documents."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from cerebro.research.errors import PlannerError


class ChromaDimensionStore:
    """Store retrieval documents in one environment-scoped Chroma collection."""

    def __init__(self, *, ttl_seconds: int = 3600) -> None:
        self._ttl_seconds = ttl_seconds
        api_key = os.environ.get("CHROMA_API_KEY", "").strip()
        tenant = os.environ.get("CHROMA_TENANT", "").strip()
        database = os.environ.get("CHROMA_DATABASE", "").strip()
        collection_name = os.environ.get("CHROMA_COLLECTION_NAME", "").strip()
        environment_name = os.environ.get("CEREBRO_ENV", os.environ.get("APP_ENV", "prod")).strip().lower()
        openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        openai_embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()

        if not api_key or not tenant or not database:
            raise PlannerError("CHROMA_API_KEY, CHROMA_TENANT, and CHROMA_DATABASE must be configured")
        if not openai_api_key:
            raise PlannerError("OPENAI_API_KEY must be configured for embeddings")

        if not collection_name:
            collection_name = self._default_collection_name(environment_name)

        self._client = chromadb.CloudClient(
            api_key=api_key,
            tenant=tenant,
            database=database,
        )
        self._embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=openai_api_key,
            model_name=openai_embedding_model,
        )
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_function,
        )

    def ingest(self, *, documents: list[dict[str, Any]], query_id: str) -> dict[str, Any]:
        now_unix = int(time.time())
        expires_at_unix = now_unix + self._ttl_seconds

        self._purge_expired(now_unix)
        ids: list[str] = []
        docs: list[str] = []
        metadatas: list[dict[str, Any]] = []
        dimension_counts: dict[str, int] = {}

        for doc in documents:
            if not isinstance(doc, dict):
                continue

            dimension_key = str(doc.get("dimension") or "").strip()
            if not dimension_key:
                continue

            content = str(doc.get("content") or "").strip()
            if not content:
                continue

            source_url = str(doc.get("source_url") or "").strip()
            source_id = str(doc.get("source_id") or "").strip()
            provider = str(doc.get("provider") or "unknown").strip()
            task_type = str(doc.get("task_type") or "unknown").strip()
            title = str(doc.get("title") or "").strip()

            # Deterministic ID means duplicate writes overwrite existing entries via upsert.
            raw_id = f"{self._collection_name}|{source_url}|{task_type}|{source_id}|{dimension_key}"
            doc_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

            metadata = {
                "dimension": dimension_key,
                "source_id": source_id,
                "source_name": str(doc.get("source_name") or ""),
                "source_url": source_url,
                "provider": provider,
                "task_type": task_type,
                "query": str(doc.get("query") or ""),
                "title": title,
                "published_date": str(doc.get("published_date") or doc.get("date") or ""),
                "relevance_score": float(doc.get("score") or 0.0),
                "agent_that_found_it": provider,
                "query_id": query_id,
                "retrieved_at_unix": now_unix,
                "expires_at_unix": expires_at_unix,
            }

            ids.append(doc_id)
            docs.append(content)
            metadatas.append(metadata)
            dimension_counts[dimension_key] = dimension_counts.get(dimension_key, 0) + 1

        if ids:
            self._collection.upsert(ids=ids, documents=docs, metadatas=metadatas)

        return {
            "ttl_seconds": self._ttl_seconds,
            "collection_name": self._collection_name,
            "total_written": len(ids),
            "by_dimension": dimension_counts,
        }

    def query(
        self,
        *,
        query_text: str,
        dimension: str | None = None,
        top_k: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query the single Chroma collection, optionally filtering by dimension."""
        self._purge_expired(int(time.time()))

        filters: dict[str, Any] = dict(where or {})
        if dimension:
            filters["dimension"] = dimension

        result = self._collection.query(
            query_texts=[query_text],
            n_results=top_k,
            where=filters or None,
            include=["documents", "metadatas", "distances"],
        )

        return {
            "collection_name": self._collection_name,
            "query_text": query_text,
            "dimension": dimension,
            "top_k": top_k,
            "result": result,
        }

    def _purge_expired(self, now_unix: int) -> None:
        try:
            self._collection.delete(where={"expires_at_unix": {"$lt": now_unix}})
        except Exception:
            # Fallback path for deployments with stricter where semantics.
            data = self._collection.get(include=["metadatas"])
            ids = data.get("ids") or []
            metadatas = data.get("metadatas") or []
            stale_ids: list[str] = []
            for doc_id, metadata in zip(ids, metadatas, strict=False):
                if not isinstance(metadata, dict):
                    continue
                expires = metadata.get("expires_at_unix")
                if isinstance(expires, (int, float)) and int(expires) < now_unix:
                    stale_ids.append(str(doc_id))
            if stale_ids:
                self._collection.delete(ids=stale_ids)

    @staticmethod
    def _default_collection_name(environment_name: str) -> str:
        if environment_name in {"dev", "development", "local"}:
            return "cerebro_dev"
        if environment_name in {"staging", "stage", "qa"}:
            return "cerebro_staging"
        return "cerebro_prod"