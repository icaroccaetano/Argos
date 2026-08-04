"""Enumerações de estado do domínio.

Herdam de `(str, Enum)` para que o valor do membro — e não o seu nome — seja o
que trafega para o banco e para o JSON.

Implementa: RN-03-01, RN-03-02
"""

from enum import Enum


class CurriculumStatus(str, Enum):
    """Estágios do pipeline de ingestão de um currículo (RN-03-01)."""

    PENDING = "pending"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"


class EvaluationStatus(str, Enum):
    """Estágios de uma avaliação de currículo × vaga (RN-03-02)."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


def enum_values(enum_class: type[Enum]) -> list[str]:
    """Lista os valores dos membros, na ordem de declaração.

    Alimenta o `values_callable` do `sa.Enum` (RT-03-04): sem ele o SQLAlchemy
    grava o *nome* do membro (`PENDING`) no tipo nativo do PostgreSQL.
    """
    return [str(member.value) for member in enum_class]
