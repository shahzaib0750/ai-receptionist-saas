"""Add business-scoped knowledge documents and embedded chunks.

Revision ID: 0010_knowledge_foundation
Revises: 0009_billing_foundation
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0010_knowledge_foundation"
down_revision = "0009_billing_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=2048), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "processing_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_knowledge_documents_processing_status",
        ),
        sa.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_knowledge_documents_file_size",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "business_id",
            name="uq_knowledge_documents_id_business",
        ),
        sa.UniqueConstraint(
            "business_id",
            "content_sha256",
            name="uq_knowledge_documents_business_sha256",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_business_created",
        "knowledge_documents",
        ["business_id", "created_at"],
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_knowledge_chunks_index",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "business_id"],
            ["knowledge_documents.id", "knowledge_documents.business_id"],
            name="fk_knowledge_chunks_document_business",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_chunks_document_index",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_business_document",
        "knowledge_chunks",
        ["business_id", "document_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_embedding_cosine",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_chunks_embedding_cosine",
        table_name="knowledge_chunks",
    )
    op.drop_index(
        "ix_knowledge_chunks_business_document",
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")
    op.drop_index(
        "ix_knowledge_documents_business_created",
        table_name="knowledge_documents",
    )
    op.drop_table("knowledge_documents")
