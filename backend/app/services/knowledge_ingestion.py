from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.document_extraction import (
    DocumentExtractionError,
    DocumentValidationError,
    extract_document_text,
    validate_upload,
)
from app.services.embedding import EmbeddingServiceError, embed_texts
from app.services.text_chunking import chunk_pages

logger = logging.getLogger(__name__)


class DocumentIngestionError(RuntimeError):
    def __init__(self, error_code: str, *, unavailable: bool = False) -> None:
        self.error_code = error_code
        self.unavailable = unavailable
        super().__init__("The document could not be processed")


class DocumentAlreadyProcessing(RuntimeError):
    pass


def ingest_document(
    db: Session,
    *,
    business_id: UUID,
    filename: str | None,
    mime_type: str | None,
    content: bytes,
    source: str | None = None,
) -> tuple[KnowledgeDocument, bool]:
    upload = validate_upload(filename, mime_type, content)
    if source is not None:
        source = source.strip() or None
        if source is not None and len(source) > 2048:
            raise DocumentValidationError("Document source exceeds the size limit")

    content_sha256 = hashlib.sha256(content).hexdigest()
    document = db.scalar(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.business_id == business_id,
            KnowledgeDocument.content_sha256 == content_sha256,
        )
        .with_for_update()
    )
    created = document is None
    if document is not None:
        if document.processing_status == "completed":
            return document, False
        if document.processing_status == "processing":
            raise DocumentAlreadyProcessing
        document.original_filename = upload.filename
        document.document_type = upload.document_type
        document.mime_type = upload.mime_type
        document.file_size_bytes = upload.file_size_bytes
        document.source = source
        document.processing_status = "processing"
        document.error_code = None
        db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.business_id == business_id,
            )
        )
    else:
        document = KnowledgeDocument(
            business_id=business_id,
            original_filename=upload.filename,
            document_type=upload.document_type,
            mime_type=upload.mime_type,
            file_size_bytes=upload.file_size_bytes,
            source=source,
            content_sha256=content_sha256,
            processing_status="processing",
        )
        db.add(document)

    try:
        db.commit()
        db.refresh(document)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business_id,
                KnowledgeDocument.content_sha256 == content_sha256,
            )
        )
        if existing is None:
            raise
        if existing.processing_status == "completed":
            return existing, False
        raise DocumentAlreadyProcessing from None

    try:
        pages = extract_document_text(upload, content)
        settings = get_settings()
        text_chunks = chunk_pages(
            pages,
            chunk_size=settings.KNOWLEDGE_CHUNK_SIZE,
            overlap=settings.KNOWLEDGE_CHUNK_OVERLAP,
        )
        if not text_chunks:
            raise DocumentExtractionError("The document contains no extractable text")
        vectors = embed_texts(
            [chunk.text for chunk in text_chunks],
            model_name=settings.KNOWLEDGE_EMBEDDING_MODEL,
            batch_size=settings.KNOWLEDGE_EMBEDDING_BATCH_SIZE,
        )
        db.add_all(
            [
                KnowledgeChunk(
                    document_id=document.id,
                    business_id=business_id,
                    chunk_index=chunk.index,
                    chunk_text=chunk.text,
                    embedding=vector,
                    embedding_model=settings.KNOWLEDGE_EMBEDDING_MODEL,
                    chunk_metadata=chunk.metadata,
                )
                for chunk, vector in zip(text_chunks, vectors, strict=True)
            ]
        )
        document.processing_status = "completed"
        document.error_code = None
        db.commit()
        db.refresh(document)
        return document, created
    except DocumentValidationError:
        db.rollback()
        _mark_failed(db, document.id, "invalid_document")
        raise
    except DocumentExtractionError as error:
        db.rollback()
        _mark_failed(db, document.id, error.error_code)
        raise DocumentIngestionError(error.error_code) from error
    except EmbeddingServiceError as error:
        db.rollback()
        _mark_failed(db, document.id, "embedding_failed")
        raise DocumentIngestionError("embedding_failed", unavailable=True) from error
    except Exception:
        db.rollback()
        logger.exception(
            "Unexpected knowledge document ingestion failure",
            extra={"business_id": str(business_id), "document_id": str(document.id)},
        )
        _mark_failed(db, document.id, "processing_failed")
        raise


def _mark_failed(db: Session, document_id: UUID, error_code: str) -> None:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise RuntimeError("Knowledge document disappeared during ingestion")
    document.processing_status = "failed"
    document.error_code = error_code
    db.commit()
