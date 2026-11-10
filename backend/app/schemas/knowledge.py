from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

KnowledgeDocumentStatus = Literal["pending", "processing", "completed", "failed"]


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    original_filename: str
    document_type: str
    mime_type: str
    file_size_bytes: int
    source: str | None
    processing_status: KnowledgeDocumentStatus
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentPage(BaseModel):
    items: list[KnowledgeDocumentRead]
    total: int
    limit: int
    offset: int
