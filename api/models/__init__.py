"""Pacote dos modelos ORM.

Todo modelo é importado aqui. Sem isso `Base.metadata` está vazio no momento
em que `migrations/env.py` o lê, e o `alembic revision --autogenerate` produz
uma migration vazia em silêncio.

Implementa: RT-03-06
"""

from api.models.base import Base
from api.models.curriculum import Curriculum
from api.models.enums import CurriculumStatus, EvaluationStatus
from api.models.evaluation import Evaluation
from api.models.mixins import SoftDeleteMixin, TimestampMixin

__all__ = [
    "Base",
    "Curriculum",
    "CurriculumStatus",
    "Evaluation",
    "EvaluationStatus",
    "SoftDeleteMixin",
    "TimestampMixin",
]