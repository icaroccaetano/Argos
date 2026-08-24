"""Testes de aceite do modelo de dados.

Implementa: CA-03-06, CA-03-07, CA-03-08, CA-03-09, CA-03-10, CA-03-11
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import CurriculumStatus, Evaluation, EvaluationStatus
from tests.factories import make_curriculum, make_evaluation


@pytest.mark.asyncio
async def test_ca_03_06_invalid_curriculum_status_is_rejected(
    session: AsyncSession,
) -> None:
    """O ENUM nativo recusa um valor fora da lista (RN-03-01).

    O erro chega como `DBAPIError` — superclasse de `DataError` — porque o
    asyncpg não traduz `InvalidTextRepresentationError` para a exceção tipada
    da PEP 249. O que o critério exige é o `InvalidTextRepresentation` do
    PostgreSQL, verificado pelo SQLSTATE `22P02`.
    """
    with pytest.raises(DBAPIError) as excinfo:
        await session.execute(
            text(
                "INSERT INTO curricula (filename, bucket_key, status) "
                "VALUES (:filename, :bucket_key, 'invalid')"
            ),
            {
                "filename": "cv.pdf",
                "bucket_key": "invalid-status.pdf",
            },
        )

    assert excinfo.value.orig.sqlstate == "22P02"
    assert "invalid input value for enum curriculum_status" in str(excinfo.value)


@pytest.mark.asyncio
async def test_ca_03_07_delete_of_evaluated_curriculum_is_blocked(
    session: AsyncSession,
) -> None:
    """`ON DELETE RESTRICT` protege o histórico de avaliação (RN-03-08)."""
    curriculum = make_curriculum()
    session.add(curriculum)
    await session.flush()
    session.add(make_evaluation(curriculum.id))
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(
            text("DELETE FROM curricula WHERE id = :id"),
            {"id": curriculum.id},
        )


@pytest.mark.asyncio
async def test_ca_03_08_jsonb_roundtrip_and_automatic_timestamps(
    session: AsyncSession,
) -> None:
    """`JSONB` volta como `list[str]`; os timestamps são do banco (RF-03-05)."""
    curriculum = make_curriculum()
    session.add(curriculum)
    await session.flush()

    evaluation = make_evaluation(
        curriculum.id,
        status=EvaluationStatus.DONE,
        score=87.5,
        strengths=["a", "b"],
        weaknesses=[],
        justification="Strong PostgreSQL background",
    )
    session.add(evaluation)
    await session.commit()

    # Releitura em sessão limpa: prova que os valores vieram do banco, não do
    # cache de identidade.
    session.expunge_all()
    stored = (
        await session.execute(select(Evaluation).where(Evaluation.id == evaluation.id))
    ).scalar_one()

    assert stored.strengths == ["a", "b"]
    assert all(isinstance(item, str) for item in stored.strengths)
    # `[]` e `NULL` não são intercambiáveis (RN-03-07).
    assert stored.weaknesses == []
    assert stored.status is EvaluationStatus.DONE
    assert stored.score == 87.5

    # Nenhum dos dois foi informado na criação.
    assert stored.created_at is not None
    assert stored.updated_at is not None
    # `TIMESTAMPTZ`: nada de timestamp ingênuo (RT-03-02).
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at.tzinfo is not None

    created_at = stored.created_at
    updated_at = stored.updated_at

    # Transação nova: `now()` do PostgreSQL é o instante da transação, então um
    # UPDATE no mesmo bloco reproduziria o mesmo valor.
    stored.justification = "Revised justification"
    await session.commit()
    await session.refresh(stored)

    assert stored.updated_at > updated_at
    assert stored.created_at == created_at


@pytest.mark.asyncio
async def test_ca_03_09_score_above_range_is_rejected(session: AsyncSession) -> None:
    """`ck_evaluations_score_range` limita o score a [0, 100] (RN-03-06)."""
    curriculum = make_curriculum()
    session.add(curriculum)
    await session.flush()
    session.add(make_evaluation(curriculum.id, score=101))

    with pytest.raises(IntegrityError) as excinfo:
        await session.commit()

    assert "ck_evaluations_score_range" in str(excinfo.value)


@pytest.mark.asyncio
async def test_ca_03_10_duplicate_bucket_key_is_rejected(
    session: AsyncSession,
) -> None:
    """Dois currículos nunca apontam para o mesmo objeto do bucket (RN-03-09)."""
    first = make_curriculum()
    session.add(first)
    await session.commit()

    session.add(make_curriculum(bucket_key=first.bucket_key))

    with pytest.raises(IntegrityError) as excinfo:
        await session.commit()

    assert "uq_curricula_bucket_key" in str(excinfo.value)


@pytest.mark.asyncio
async def test_ca_03_11_same_curriculum_can_be_evaluated_twice(
    session: AsyncSession,
) -> None:
    """Reavaliar contra a mesma vaga é operação legítima (RN-03-10)."""
    curriculum = make_curriculum()
    session.add(curriculum)
    await session.flush()

    job_description = "Staff engineer, distributed systems"
    first = make_evaluation(curriculum.id, job_description=job_description)
    second = make_evaluation(curriculum.id, job_description=job_description)
    session.add_all([first, second])
    await session.commit()

    stored = (
        (
            await session.execute(
                select(Evaluation).where(Evaluation.curriculum_id == curriculum.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(stored) == 2
    assert {row.id for row in stored} == {first.id, second.id}
    assert {row.job_description for row in stored} == {job_description}
    # Ambas nascem em `pending` (RN-03-02), e o currículo em `pending`
    # (RN-03-01).
    assert {row.status for row in stored} == {EvaluationStatus.PENDING}
    assert curriculum.status is CurriculumStatus.PENDING
