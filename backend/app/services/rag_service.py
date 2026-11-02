from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import settings


class RAGService:
    _memory_index: ClassVar[dict[str, list[dict[str, Any]]]] = {}
    _policy_chunks: ClassVar[list[dict[str, Any]] | None] = None

    def __init__(self, use_qdrant: bool = True) -> None:
        self.openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.qdrant_client = (
            QdrantClient(url=settings.qdrant_url)
            if use_qdrant and settings.qdrant_url
            else None
        )

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return []
        if len(cleaned) <= chunk_size:
            return [cleaned]

        chunks: list[str] = []
        start = 0
        while start < len(cleaned):
            end = min(start + chunk_size, len(cleaned))
            segment = cleaned[start:end]
            if end < len(cleaned):
                last_space = segment.rfind(" ")
                if last_space > chunk_size * 0.6:
                    end = start + last_space
                    segment = cleaned[start:end]
            chunks.append(segment.strip())
            start = max(start + 1, end - overlap)
        return [chunk for chunk in chunks if chunk]

    def _content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _embedding_vector(self, text: str) -> list[float]:
        if not self.openai_client:
            return [0.0] * 1536
        response = self.openai_client.embeddings.create(
            model=settings.openai_embedding_model,
            input=text,
        )
        item = response.data[0]
        return list(item.embedding)

    def ensure_collection(self, collection_name: str = "support_docs") -> None:
        if not self.qdrant_client:
            return
        try:
            self.qdrant_client.get_collection(collection_name=collection_name)
        except UnexpectedResponse as exc:
            if exc.status_code != 404:
                raise
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

    def index_document(self, filename: str, content: str, tenant_id: str = "tenant-demo") -> dict[str, Any]:
        chunks = self.chunk_text(content)
        document_id = str(uuid4())
        if not chunks:
            return {"document_id": document_id, "chunks": [], "index_status": "empty"}

        self._memory_index.setdefault(tenant_id, [])
        indexed_chunks: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            chunk_id = f"{document_id}:{index}"
            payload = {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "tenant_id": tenant_id,
                "filename": filename,
                "content": chunk,
                "content_hash": self._content_hash(chunk),
                "metadata": {"tenant_id": tenant_id, "filename": filename, "chunk_index": index},
            }
            indexed_chunks.append(payload)
            self._memory_index[tenant_id].append(payload)

        self.ensure_collection()
        if self.qdrant_client and self.openai_client:
            for payload in indexed_chunks:
                vector = self._embedding_vector(payload["content"])
                self.qdrant_client.upsert(
                    collection_name="support_docs",
                    points=[
                        PointStruct(
                            id=payload["chunk_id"],
                            vector=vector,
                            payload={
                                "tenant_id": tenant_id,
                                "document_id": document_id,
                                "filename": filename,
                                "chunk_id": payload["chunk_id"],
                                "content": payload["content"],
                                "chunk_index": payload["metadata"]["chunk_index"],
                            },
                        )
                    ],
                )
            index_status = "indexed"
        else:
            index_status = "cached_local" if self.openai_client is None else "indexed_without_embeddings"

        return {
            "document_id": document_id,
            "chunks": indexed_chunks,
            "index_status": index_status,
        }

    def search(self, query: str, tenant_id: str = "tenant-demo", top_k: int = 5) -> list[dict[str, Any]]:
        tenant_chunks = self._memory_index.get(tenant_id, [])
        if self.qdrant_client and self.openai_client:
            query_vector = self._embedding_vector(query)
            response = self.qdrant_client.query_points(
                collection_name="support_docs",
                query=query_vector,
                limit=top_k,
                with_payload=True,
                query_filter=Filter(
                    must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
                ),
            )
            return [
                {
                    "chunk_id": point.payload["chunk_id"],
                    "document_id": point.payload["document_id"],
                    "content": point.payload["content"],
                    "metadata": {
                        "tenant_id": point.payload["tenant_id"],
                        "filename": point.payload["filename"],
                        "chunk_index": point.payload.get("chunk_index"),
                    },
                }
                for point in response.points
            ]

        query_terms = {token.lower() for token in re.findall(r"[a-zA-Z0-9]+", query)}
        if not query_terms or not tenant_chunks:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in tenant_chunks:
            content = chunk["content"].lower()
            score = sum(1 for term in query_terms if term in content)
            if score:
                scored.append((float(score), chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for _, chunk in scored[:top_k]:
            results.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "content": chunk["content"],
                    "metadata": chunk["metadata"],
                }
            )
        return results

    def search_policy_context(
        self, query: str, tenant_id: str = "tenant-demo", top_k: int = 5
    ) -> list[dict[str, Any]]:
        if tenant_id == "tenant-demo" and RAGService._policy_chunks is None:
            docs_path = Path(__file__).resolve().parents[3] / "sample-documents"
            policy_chunks: list[dict[str, Any]] = []
            if docs_path.exists():
                for document_path in sorted(docs_path.glob("*.md")):
                    content = document_path.read_text(encoding="utf-8")
                    for index, chunk in enumerate(self.chunk_text(content)):
                        policy_chunks.append(
                            {
                                "chunk_id": f"sample:{document_path.stem}:{index}",
                                "document_id": f"sample:{document_path.stem}",
                                "content": chunk,
                                "metadata": {
                                    "tenant_id": "tenant-demo",
                                    "filename": document_path.name,
                                    "chunk_index": index,
                                },
                            }
                        )
            RAGService._policy_chunks = policy_chunks

        query_terms = {token.lower() for token in re.findall(r"[a-zA-Z0-9]+", query)}
        candidates = self._memory_index.get(tenant_id, [])
        if tenant_id == "tenant-demo":
            candidates = [*candidates, *(RAGService._policy_chunks or [])]
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in candidates:
            content_terms = set(re.findall(r"[a-zA-Z0-9]+", chunk["content"].lower()))
            score = len(query_terms.intersection(content_terms))
            if score:
                scored.append((float(score), chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        seen_chunks: set[str] = set()
        for _, chunk in scored:
            if chunk["chunk_id"] in seen_chunks:
                continue
            seen_chunks.add(chunk["chunk_id"])
            results.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "content": chunk["content"],
                    "metadata": chunk.get("metadata", {}),
                }
            )
            if len(results) == top_k:
                break
        return results
