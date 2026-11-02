from pydantic import BaseModel, Field


class DocumentUploadRequest(BaseModel):
    tenant_id: str = "tenant-demo"
    filename: str = "refund-policy.md"
    content: str = ""


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    tenant_id: str = "tenant-demo"
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievalResult(BaseModel):
    query: str
    results: list[DocumentChunk]
    index_status: str = "ok"


class DocumentUploadResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    chunks: int
    index_status: str
