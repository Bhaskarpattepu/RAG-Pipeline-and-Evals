from app.services.rag_service import RAGService


def test_chunk_text_splits_large_content() -> None:
    service = RAGService()
    content = "Refund policy summary. " * 200
    chunks = service.chunk_text(content, chunk_size=250, overlap=50)
    assert len(chunks) > 1
    assert all(chunk for chunk in chunks)


def test_search_returns_local_policy_matches() -> None:
    service = RAGService(use_qdrant=False)
    content = "Refunds are approved within 7 business days for canceled subscriptions. Payment failures due to expired cards are reviewed manually."
    service._memory_index["tenant-demo"] = [
        {
            "chunk_id": "doc-1:0",
            "document_id": "doc-1",
            "tenant_id": "tenant-demo",
            "filename": "refund-policy.md",
            "content": content,
            "content_hash": "abc",
            "metadata": {"tenant_id": "tenant-demo", "filename": "refund-policy.md", "chunk_index": 0},
        }
    ]

    results = service.search("refund policy", tenant_id="tenant-demo", top_k=5)
    assert len(results) == 1
    assert "refund" in results[0]["content"].lower()
