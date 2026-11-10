# Hybrid RAG foundation

This document covers the initial business-scoped document-ingestion foundation.
Semantic retrieval and Vapi custom tools are intentionally not part of this phase.

## Requirements

The backend runs in `backend/.venv`. The RAG dependencies are pinned in
`requirements.txt`. The PyTorch dependency is the CPU wheel; install using the
CPU wheel index to avoid GPU/CUDA packages:

```bash
cd backend
.venv/bin/python -m pip install --only-binary=:all: \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  -r requirements.txt
```

The embedding model is loaded lazily from Hugging Face when the first document is
ingested. The first request therefore requires network access to download the
model unless it is already cached.

## PostgreSQL and migration

Install the PostgreSQL 18 pgvector server package for the host OS before
migrating. On Ubuntu 26.04, the package is `postgresql-18-pgvector`. A database
administrator must enable the extension in the development database before the
application role can apply the migration:

```bash
sudo -u postgres psql -d <development-database> \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

The migration also contains `CREATE EXTENSION IF NOT EXISTS vector` as a
declaration of its requirement; it cannot grant the application role elevated
extension privileges. It creates the knowledge tables and a cosine HNSW index.
Check the current revision and upgrade only the intended development database:

```bash
cd backend
.venv/bin/alembic current
.venv/bin/alembic upgrade head
```

The migration downgrade removes its tables and indexes. It intentionally leaves
the `vector` extension installed because it may have existed before this
migration or be used by other database objects.

## Configuration

Knowledge settings are optional environment settings with conservative defaults:

| Setting | Default | Description |
|---|---:|---|
| `KNOWLEDGE_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Sentence Transformers model identifier |
| `KNOWLEDGE_EMBEDDING_DIMENSIONS` | `384` | Fixed to this model's output size |
| `KNOWLEDGE_EMBEDDING_BATCH_SIZE` | `8` | CPU embedding batch size |
| `KNOWLEDGE_CHUNK_SIZE` | `1000` | Maximum chunk characters |
| `KNOWLEDGE_CHUNK_OVERLAP` | `150` | Approximate overlap in characters |
| `KNOWLEDGE_MAX_UPLOAD_BYTES` | `10485760` | Maximum uploaded file size |
| `KNOWLEDGE_MAX_EXTRACTED_CHARACTERS` | `1000000` | Maximum extracted text |
| `KNOWLEDGE_MAX_PDF_PAGES` | `500` | Maximum PDF page count |

The current model and schema are fixed at 384 dimensions. Changing the model to
one with another output dimension requires a reviewed schema migration and
re-embedding existing chunks.

## Ingestion flow

`POST /api/v1/knowledge/documents?business_id=<uuid>` accepts a multipart `upload`
and optional `source`. It requires an authenticated business owner or admin
with operational-resource management permission. The service validates
filename, extension, MIME type and size; extracts UTF-8 text or PDF page text;
cleans and chunks the text; generates normalized CPU embeddings; and commits all
chunks with the document completion status in one transaction. Extraction and
embedding failures persist a failed document status without partial chunks.
Re-uploading the same file for the same business retries a failed ingestion or
returns the already completed document.

Supported formats are PDF (`application/pdf`), TXT (`text/plain`), and Markdown
(`text/markdown`, `text/x-markdown`, or `text/plain`). Uploaded content is read
in memory only; it is not executed or written to a filesystem. Source files are
not retained, so retry requires uploading the file again.

## Tests

Run the unit/API tests with:

```bash
cd backend
.venv/bin/python -m pytest tests/test_knowledge.py
```

The PostgreSQL integrity test runs only when `VAPI_TEST_DATABASE_URL` points to
a local, isolated database named `vapi_test_*` where pgvector is enabled:

```bash
.venv/bin/python -m pytest tests/test_knowledge_postgres.py
```

SQLite tests cover extraction, chunking, mocked embeddings, ingestion
transactions, and API authorization. PostgreSQL-specific vector and composite
foreign-key behavior must be verified using PostgreSQL; SQLite is not a
substitute for vector search tests.

## Current limitations

Knowledge documents can be uploaded, processed, listed, read, and deleted.
There is not yet a semantic retrieval API, structured business service catalog,
hybrid retrieval/reranking pipeline, vector query service, or Vapi custom tool.
