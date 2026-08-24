"""Modelo ORM da avaliação de um currículo contra uma descrição de vaga.

Implementa: RF-03-02, RF-03-03, RF-03-04, RF-03-05, RN-03-02, RN-03-04,
RN-03-05, RN-03-06, RN-03-07, RN-03-08, RN-03-10, RT-03-01, RT-03-02,
RT-03-04, RT-03-05, RT-03-08, RT-03-09
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Double,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base
from api.models.enums import EvaluationStatus, enum_values
from api.models.mixins import SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from api.models.curriculum import Curriculum


class Evaluation(Base, TimestampMixin, SoftDeleteMixin):
    """Resultado estruturado de uma avaliação currículo × vaga."""

    __tablename__ = "evaluations"
    __table_args__ = (
        # `NULL` escapa da checagem por três valores: a restrição só se aplica
        # a scores já gravados (RN-03-06).
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_evaluations_score_range",
        ),
        Index("ix_evaluations_curriculum_id", "curriculum_id"),
        Index("ix_evaluations_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    curriculum_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # `RESTRICT`: o histórico de avaliação não pode sumir por cascata de um
        # DELETE físico do currículo (RN-03-08).
        ForeignKey(
            "curricula.id",
            ondelete="RESTRICT",
            name="fk_evaluations_curriculum_id_curricula",
        ),
        nullable=False,
    )
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        Enum(
            EvaluationStatus,
            name="evaluation_status",
            values_callable=enum_values,
        ),
        nullable=False,
        default=EvaluationStatus.PENDING,
        server_default=EvaluationStatus.PENDING.value,
    )
    score: Mapped[float | None] = mapped_column(Double, nullable=True)
    # `[]` significa "avaliado, nada encontrado"; `NULL`, "ainda não avaliado"
    # (RN-03-07). Os dois casos não são intercambiáveis.
    strengths: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    weaknesses: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Obrigatório desde a criação: o modelo é resolvido antes de enfileirar o
    # trabalho, o que torna a avaliação reprodutível (RN-03-05).
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)

    curriculum: Mapped[Curriculum] = relationship(
        back_populates="evaluations",
        lazy="raise",
    )
