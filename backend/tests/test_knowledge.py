from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models.business import Business, BusinessMember, BusinessRole
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services import document_extraction, embedding, knowledge_ingestion
from app.services.document_extraction import (
    DocumentExtractionError,
    UnsupportedDocumentType,
    extract_document_text,
    validate_upload,
)
from app.services.embedding import EmbeddingServiceError, embed_text, embed_texts
from app.services.knowledge_ingestion import ingest_document
from app.services.text_chunking import chunk_pages


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    yield factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _create_workspace(
    session_factory: sessionmaker[Session],
    *,
    email: str,
) -> tuple[UUID, UUID, str]:
    from app.core.security import create_access_token
    from app.models.user import User

    with session_factory.begin() as db:
        user = User(
            full_name="Knowledge test",
            email=email,
            password_hash=hash_password("test-password"),
        )
        db.add(user)
        db.flush()
        business = Business(name=f"Workspace {email}", owner_user_id=user.id)
        db.add(business)
        db.flush()
        db.add(
            BusinessMember(
                business_id=business.id,
                user_id=user.id,
                role=BusinessRole.OWNER,
            )
        )
        user_id, business_id, version = user.id, business.id, user.token_version
    return user_id, business_id, create_access_token(user_id, version)


def _pdf_with_text(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)


def test_document_extraction_accepts_pdf_text_and_markdown() -> None:
    pdf = _pdf_with_text("Clinic services")
    pdf_upload = validate_upload("details.pdf", "application/pdf", pdf)
    assert "Clinic services" in extract_document_text(pdf_upload, pdf)[0]

    txt = b"  Weekday hours\r\n9 AM to 5 PM "
    txt_upload = validate_upload("hours.txt", "text/plain", txt)
    assert extract_document_text(txt_upload, txt) == ("Weekday hours\n9 AM to 5 PM",)

    markdown = b"# Services\n\nDental cleaning"
    md_upload = validate_upload("services.md", "text/markdown", markdown)
    assert extract_document_text(md_upload, markdown) == (
        "# Services\n\nDental cleaning",
    )


def test_document_extraction_rejects_bad_types_empty_and_invalid_content() -> None:
    with pytest.raises(UnsupportedDocumentType):
        validate_upload("script.exe", "application/octet-stream", b"x")
    with pytest.raises(UnsupportedDocumentType):
        validate_upload("guide.pdf", "text/plain", b"x")
    with pytest.raises(document_extraction.DocumentValidationError):
        validate_upload("empty.txt", "text/plain", b"")
    with pytest.raises(DocumentExtractionError):
        upload = validate_upload("bad.pdf", "application/pdf", b"not a pdf")
        extract_document_text(upload, b"not a pdf")
    with pytest.raises(DocumentExtractionError):
        upload = validate_upload("bad.txt", "text/plain", b"\xff")
        extract_document_text(upload, b"\xff")


def test_upload_filename_is_not_used_as_a_path() -> None:
    upload = validate_upload("../private/guide.txt", "text/plain", b"Public text")
    assert upload.filename == "guide.txt"


def test_chunking_is_deterministic_ordered_and_preserves_page_metadata() -> None:
    pages = [
        "First sentence. Second sentence. Third sentence. Fourth sentence.",
        "Another page has a short note.",
    ]
    first = chunk_pages(pages, chunk_size=32, overlap=8)
    second = chunk_pages(pages, chunk_size=32, overlap=8)

    assert first == second
    assert [chunk.index for chunk in first] == list(range(len(first)))
    assert first[0].metadata == {"page_number": 1}
    assert first[-1].metadata == {"page_number": 2}
    assert all(0 < len(chunk.text) <= 32 for chunk in first)


def test_chunking_handles_short_long_empty_and_overlap() -> None:
    short = chunk_pages(["Short text."], chunk_size=50, overlap=10)
    assert [chunk.text for chunk in short] == ["Short text."]
    assert chunk_pages(["  ", ""], chunk_size=50, overlap=10) == []

    text = "One two three four five six seven eight nine ten. " * 8
    chunks = chunk_pages([text], chunk_size=64, overlap=16)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 64 for chunk in chunks)
    assert any(
        chunks[index].text[-8:] in chunks[index + 1].text
        for index in range(len(chunks) - 1)
    )


def test_embedding_outputs_normalized_384_dimension_vectors_and_caches_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loads: list[str] = []
    batches: list[tuple[int, int]] = []

    class FakeModel:
        def encode(self, texts, **kwargs):
            batches.append((len(texts), kwargs["batch_size"]))
            return np.tile(np.array([1.0] + [0.0] * 383), (len(texts), 1))

    def fake_loader(model_name: str):
        loads.append(model_name)
        return FakeModel()

    monkeypatch.setattr(embedding, "_load_model", fake_loader)
    vectors = embed_texts(["first", "second"], model_name="test-model", batch_size=2)
    one_vector = embed_text("third", model_name="test-model")

    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert sum(value * value for value in vectors[0]) == pytest.approx(1.0)
    assert len(one_vector) == 384
    assert loads == ["test-model", "test-model"]
    assert batches == [(2, 2), (1, 8)]


@pytest.mark.parametrize("texts", [[], [""], ["  "]])
def test_embedding_rejects_empty_inputs(texts: list[str]) -> None:
    with pytest.raises(ValueError):
        embed_texts(texts)


def test_embedding_handles_model_load_inference_and_dimension_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_loader(_model_name: str):
        raise EmbeddingServiceError("load failed")

    monkeypatch.setattr(embedding, "_load_model", failed_loader)
    with pytest.raises(EmbeddingServiceError):
        embed_text("text")

    class WrongDimensionModel:
        def encode(self, _texts, **_kwargs):
            return np.ones((1, 3))

    monkeypatch.setattr(embedding, "_load_model", lambda _name: WrongDimensionModel())
    with pytest.raises(EmbeddingServiceError):
        embed_text("text")

    class FailedInferenceModel:
        def encode(self, _texts, **_kwargs):
            raise RuntimeError("model error")

    monkeypatch.setattr(embedding, "_load_model", lambda _name: FailedInferenceModel())
    with pytest.raises(EmbeddingServiceError):
        embed_text("text")


def test_ingestion_persists_document_and_chunks_and_is_idempotent(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, business_id, _ = _create_workspace(session_factory, email="ingest@example.test")
    monkeypatch.setattr(
        knowledge_ingestion,
        "embed_texts",
        lambda texts, **_kwargs: [[1.0] + [0.0] * 383 for _ in texts],
    )

    with session_factory() as db:
        document, created = ingest_document(
            db,
            business_id=business_id,
            filename="services.txt",
            mime_type="text/plain",
            content=b"Cleaning costs 100 dollars. Whitening costs 200 dollars.",
        )
        document_id = document.id
        assert created
        assert document.processing_status == "completed"
        assert document.error_code is None

    with session_factory() as db:
        chunks = db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        ).all()
        assert len(chunks) == 1
        assert chunks[0].business_id == business_id
        assert chunks[0].embedding_model
        assert chunks[0].chunk_metadata == {"page_number": 1}
        duplicate, created = ingest_document(
            db,
            business_id=business_id,
            filename="services.txt",
            mime_type="text/plain",
            content=b"Cleaning costs 100 dollars. Whitening costs 200 dollars.",
        )
        assert duplicate.id == document_id
        assert not created


def test_failed_ingestion_sets_status_and_retry_replaces_no_partial_chunks(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, business_id, _ = _create_workspace(session_factory, email="retry@example.test")

    def fail_embeddings(_texts, **_kwargs):
        raise EmbeddingServiceError("inference failed")

    monkeypatch.setattr(knowledge_ingestion, "embed_texts", fail_embeddings)
    with session_factory() as db:
        with pytest.raises(knowledge_ingestion.DocumentIngestionError):
            ingest_document(
                db,
                business_id=business_id,
                filename="faq.md",
                mime_type="text/markdown",
                content=b"# FAQ\n\nWe close at 5 PM.",
            )
        document = db.scalar(select(KnowledgeDocument))
        assert document is not None
        document_id = document.id
        assert document.processing_status == "failed"
        assert document.error_code == "embedding_failed"
        assert db.scalar(select(KnowledgeChunk.id)) is None

    monkeypatch.setattr(
        knowledge_ingestion,
        "embed_texts",
        lambda texts, **_kwargs: [[1.0] + [0.0] * 383 for _ in texts],
    )
    with session_factory() as db:
        retried, created = ingest_document(
            db,
            business_id=business_id,
            filename="faq.md",
            mime_type="text/markdown",
            content=b"# FAQ\n\nWe close at 5 PM.",
        )
        assert retried.id == document_id
        assert not created
        assert retried.processing_status == "completed"
        assert db.scalar(select(KnowledgeChunk.id)) is not None


def test_failed_extraction_is_recorded(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, business_id, _ = _create_workspace(session_factory, email="extract@example.test")
    monkeypatch.setattr(
        knowledge_ingestion,
        "embed_texts",
        lambda texts, **_kwargs: [[1.0] + [0.0] * 383 for _ in texts],
    )
    with session_factory() as db:
        with pytest.raises(knowledge_ingestion.DocumentIngestionError):
            ingest_document(
                db,
                business_id=business_id,
                filename="empty.pdf",
                mime_type="application/pdf",
                content=b"%PDF-1.4\n%%EOF",
            )
        document = db.scalar(select(KnowledgeDocument))
        assert document is not None
        assert document.processing_status == "failed"
        assert document.error_code == "extraction_failed"
        assert db.scalar(select(KnowledgeChunk.id)) is None


def test_knowledge_api_requires_membership_and_scopes_document_operations(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, business_a, token_a = _create_workspace(
        session_factory,
        email="tenant-a@example.test",
    )
    _, business_b, token_b = _create_workspace(
        session_factory,
        email="tenant-b@example.test",
    )
    monkeypatch.setattr(
        knowledge_ingestion,
        "embed_texts",
        lambda texts, **_kwargs: [[1.0] + [0.0] * 383 for _ in texts],
    )
    response = client.post(
        f"/api/v1/knowledge/documents?business_id={business_b}",
        headers={"Authorization": f"Bearer {token_b}"},
        files={"upload": ("business.txt", b"Business B information", "text/plain")},
    )
    assert response.status_code == 201
    document_id = response.json()["id"]

    headers_a = {"Authorization": f"Bearer {token_a}"}
    assert (
        client.get(
            f"/api/v1/knowledge/documents?business_id={business_b}",
            headers=headers_a,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/knowledge/documents/{document_id}?business_id={business_a}",
            headers=headers_a,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/knowledge/documents/{document_id}?business_id={business_a}",
            headers=headers_a,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/knowledge/documents?business_id={business_b}",
            headers=headers_a,
            files={"upload": ("private.txt", b"Not authorized", "text/plain")},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/knowledge/documents").status_code == 401
