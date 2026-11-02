from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.rag import DocumentUploadRequest, DocumentUploadResponse, RetrievalRequest, RetrievalResult
from app.services.rag_service import RAGService

router = APIRouter(tags=["rag"])


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Form("tenant-demo"),
) -> DocumentUploadResponse:
    if file.content_type not in {"text/markdown", "text/plain", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Only markdown and text files are supported in this phase")

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    service = RAGService()
    result = service.index_document(filename=file.filename or "document.txt", content=text, tenant_id=tenant_id)
    return DocumentUploadResponse(
        document_id=result["document_id"],
        tenant_id=tenant_id,
        filename=file.filename or "document.txt",
        chunks=len(result["chunks"]),
        index_status=result["index_status"],
    )


@router.post("/rag/search", response_model=RetrievalResult)
def search_documents(payload: RetrievalRequest) -> RetrievalResult:
    service = RAGService()
    results = service.search(query=payload.query, tenant_id=payload.tenant_id, top_k=payload.top_k)
    return RetrievalResult(
        query=payload.query,
        results=[
            {
                "chunk_id": item["chunk_id"],
                "document_id": item["document_id"],
                "content": item["content"],
                "metadata": item.get("metadata", {}),
            }
            for item in results
        ],
        index_status="ok" if results else "not_found",
    )


@router.post("/documents", response_model=DocumentUploadResponse)
def create_document(payload: DocumentUploadRequest) -> DocumentUploadResponse:
    service = RAGService()
    result = service.index_document(filename=payload.filename, content=payload.content, tenant_id=payload.tenant_id)
    return DocumentUploadResponse(
        document_id=result["document_id"],
        tenant_id=payload.tenant_id,
        filename=payload.filename,
        chunks=len(result["chunks"]),
        index_status=result["index_status"],
    )
