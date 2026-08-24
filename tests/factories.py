"""Construtores de entidades para as duas camadas da suíte.

Funções puras: constroem a instância e devolvem. Não recebem sessão, não
persistem, não commitam — quem persiste é o teste (spec 07 §3.2).

Implementa: RF-07-04, RT-07-03
"""

import uuid

from api.models import Curriculum, Evaluation


def make_curriculum(**overrides: object) -> Curriculum:
    """Currículo válido com `bucket_key` único (RN-03-09).

    O `uuid4()` garante unicidade dentro de uma execução. O isolamento entre
    execuções é do banco dedicado, não de um prefixo no nome do objeto
    (RN-07-06).
    """
    values: dict[str, object] = {
        "filename": "cv.pdf",
        "bucket_key": f"{uuid.uuid4()}.pdf",
    }
    values.update(overrides)
    return Curriculum(**values)


def make_evaluation(curriculum_id: uuid.UUID, **overrides: object) -> Evaluation:
    """Avaliação válida: `model_version` é obrigatório na criação (RN-03-05)."""
    values: dict[str, object] = {
        "curriculum_id": curriculum_id,
        "job_description": "Backend engineer, Python and PostgreSQL",
        "model_version": "test-model-v1",
    }
    values.update(overrides)
    return Evaluation(**values)
