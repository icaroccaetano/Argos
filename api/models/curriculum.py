"""Modelo ORM do currículo enviado para ingestão.

Implementa: RF-03-01, RF-03-04, RF-03-05, RN-03-01, RN-03-03, RN-03-08,
RN-03-09, RT-03-01, RT-03-02, RT-03-04, RT-03-05, RT-03-08, RT-03-09
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base
from api.models.enums import CurriculumStatus, enum_values
from api.models.mixins import SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from api.models.evaluation import Evaluation


class Curriculum(Base, TimestampMixin, SoftDeleteMixin):
    """Currículo em PDF e o estágio atual do seu pipeline de ingestão."""

    __tablename__ = "curricula"
    __table_args__ = (
        # Nome explícito (RT-03-09): `unique=True` na coluna produziria
        # `curricula_bucket_key_key`, gerado pelo banco e não portável.
        UniqueConstraint("bucket_key", name="uq_curricula_bucket_key"),
        Index("ix_curricula_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        # O default do Python dá o id ao ORM antes do flush; o do banco cobre
        # inserts feitos fora do ORM (RT-03-05).
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    bucket_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[CurriculumStatus] = mapped_column(
        Enum(
            CurriculumStatus,
            name="curriculum_status",
            values_callable=enum_values,
        ),
        nullable=False,
        default=CurriculumStatus.PENDING,
        server_default=CurriculumStatus.PENDING.value,
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluations: Mapped[list[Evaluation]] = relationship(
        back_populates="curriculum",
        # Lazy loading implícito levanta `MissingGreenlet` em contexto
        # assíncrono (§3.4). Quem precisa da coleção usa `selectinload()`.
        lazy="raise",
    )