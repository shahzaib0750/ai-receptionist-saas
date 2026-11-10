from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

from pypdf import PdfReader

from app.core.config import get_settings

_SUPPORTED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/x-markdown", "text/plain"},
}
_MAX_FILENAME_LENGTH = 255


class DocumentValidationError(ValueError):
    status_code = 422
    error_code = "invalid_document"


class UnsupportedDocumentType(DocumentValidationError):
    status_code = 415
    error_code = "unsupported_document_type"


class DocumentTooLarge(DocumentValidationError):
    status_code = 413
    error_code = "document_too_large"


class DocumentExtractionError(ValueError):
    error_code = "extraction_failed"


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    document_type: str
    mime_type: str
    file_size_bytes: int


def validate_upload(
    filename: str | None,
    mime_type: str | None,
    content: bytes,
) -> ValidatedUpload:
    if not isinstance(content, bytes):
        raise DocumentValidationError("Document content must be bytes")
    if not content:
        raise DocumentValidationError("The uploaded document is empty")
    if len(content) > get_settings().KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise DocumentTooLarge("The uploaded document exceeds the size limit")
    if not filename or not isinstance(filename, str):
        raise DocumentValidationError("A document filename is required")

    safe_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    safe_filename = "".join(
        character
        for character in safe_filename
        if unicodedata.category(character) not in {"Cc", "Cf"}
    ).strip()
    if not safe_filename or safe_filename in {".", ".."}:
        raise DocumentValidationError("A valid document filename is required")
    safe_filename = safe_filename[:_MAX_FILENAME_LENGTH]
    extension = PurePosixPath(safe_filename).suffix.casefold()
    allowed_mime_types = _SUPPORTED_MIME_TYPES.get(extension)
    if allowed_mime_types is None:
        raise UnsupportedDocumentType(
            "Only PDF, TXT, and Markdown documents are supported"
        )

    normalized_mime_type = (mime_type or "").split(";", 1)[0].strip().casefold()
    if normalized_mime_type not in allowed_mime_types:
        raise UnsupportedDocumentType(
            "The document filename and MIME type are not supported together"
        )

    return ValidatedUpload(
        filename=safe_filename,
        document_type={".pdf": "pdf", ".txt": "text", ".md": "markdown"}[extension],
        mime_type=normalized_mime_type,
        file_size_bytes=len(content),
    )


def _clean_text(value: str) -> str:
    value = unicodedata.normalize(
        "NFKC", value.replace("\r\n", "\n").replace("\r", "\n")
    )
    value = "".join(
        character
        for character in value
        if character in "\n\t" or unicodedata.category(character) not in {"Cc", "Cf"}
    )
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def extract_document_text(
    upload: ValidatedUpload,
    content: bytes,
) -> tuple[str, ...]:
    if upload.document_type in {"text", "markdown"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise DocumentExtractionError(
                "Text documents must use UTF-8 encoding"
            ) from error
        if "\x00" in text:
            raise DocumentExtractionError("Text document contains invalid characters")
        pages = (_clean_text(text),)
    else:
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise DocumentExtractionError(
                    "Encrypted PDF documents are not supported"
                )
            if len(reader.pages) > get_settings().KNOWLEDGE_MAX_PDF_PAGES:
                raise DocumentTooLarge("The PDF contains too many pages")
            pages = tuple(
                _clean_text(page.extract_text() or "") for page in reader.pages
            )
        except DocumentValidationError:
            raise
        except Exception as error:
            raise DocumentExtractionError("The PDF could not be read") from error

    if not any(pages):
        raise DocumentExtractionError("The document contains no extractable text")
    if (
        sum(len(page) for page in pages)
        > get_settings().KNOWLEDGE_MAX_EXTRACTED_CHARACTERS
    ):
        raise DocumentTooLarge("The extracted document text exceeds the size limit")
    return pages
