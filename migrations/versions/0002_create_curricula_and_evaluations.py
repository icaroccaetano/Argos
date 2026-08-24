"""create curricula and evaluations

Implementa: RF-03-01, RF-03-02, RF-03-03, RF-03-04, RF-03-05, RT-03-04,
RT-03-07, RT-03-09

Revision ID: 0002_curricula_evaluations
Revises: 0001_enable_pgvector
Create Date: 2026-08-04

O id é mais curto que o nome do arquivo porque `alembic_version.version_num` é
`VARCHAR(32)`: `0002_create_curricula_and_evaluations` tem 38 caracteres e
falha no `UPDATE` ao final do upgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_curricula_evaluations"
down_revision: str | None = "0001_enable_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `create_type=False`: os tipos são criados e removidos explicitamente abaixo
# (RT-03-04). Deixar o `create_table` criá-los faria o `downgrade` derrubar as
# tabelas e abandonar os tipos, quebrando o ciclo downgrade → upgrade com
# `type already exists`.
curriculum_status = postgresql.ENUM(
    "pending",
    "parsing",
    "embedding",
    "ready",
    "error",
    name="curriculum_status",
    create_type=False,
)
evaluation_status = postgresql.ENUM(
    "pending",
    "processing",
    "done",
    "error",
    name="evaluation_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    curriculum_status.create(bind, checkfirst=False)
    evaluation_status.create(bind, checkfirst=False)

    op.create_table(
        "curricula",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("bucket_key", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            curriculum_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_curricula"),
        sa.UniqueConstraint("bucket_key", name="uq_curricula_bucket_key"),
    )
    op.create_index("ix_curricula_status", "curricula", ["status"])

    op.create_table(
        "evaluations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("curriculum_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            evaluation_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("score", sa.Double(), nullable=True),
        sa.Column("strengths", postgresql.JSONB(), nullable=True),
        sa.Column("weaknesses", postgresql.JSONB(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_evaluations_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_id"],
            ["curricula.id"],
            name="fk_evaluations_curriculum_id_curricula",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluations"),
    )
    op.create_index("ix_evaluations_curriculum_id", "evaluations", ["curriculum_id"])
    op.create_index("ix_evaluations_status", "evaluations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_evaluations_status", table_name="evaluations")
    op.drop_index("ix_evaluations_curriculum_id", table_name="evaluations")
    op.drop_table("evaluations")

    op.drop_index("ix_curricula_status", table_name="curricula")
    op.drop_table("curricula")

    bind = op.get_bind()
    evaluation_status.drop(bind, checkfirst=False)
    curriculum_status.drop(bind, checkfirst=False)
