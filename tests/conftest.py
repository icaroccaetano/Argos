"""Fixtures dos testes que tocam o banco real.

Os testes de modelo verificam comportamento do PostgreSQL — ENUM nativo,
`JSONB`, `CHECK`, `FOREIGN KEY`, defaults de servidor. Nada disso existe fora
do banco, então esta suíte roda contra o schema já migrado
(`alembic upgrade head`), conforme spec 01 §3.5.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import async_session_factory, engine
from api.models import Curriculum, Evaluation

TEST_BUCKET_PREFIX = "test/"


def make_curriculum(**overrides: object) -> Curriculum:
    """Currículo válido com `bucket_key` único no namespace de teste.

    O prefixo é o que permite ao teardown distinguir o que a suíte criou do
    que já estava no banco.
    """
    values: dict[str, object] = {
        "filename": "cv.pdf",
        "bucket_key": f"{TEST_BUCKET_PREFIX}{uuid.uuid4()}.pdf",
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


async def _purge(session: AsyncSession) -> None:
    """Remove fisicamente as linhas do namespace de teste.

    As avaliações saem primeiro: a FK é `ON DELETE RESTRICT` (RN-03-08) e
    apagar o currículo antes seria bloqueado pelo banco.
    """
    pattern = {"pattern": f"{TEST_BUCKET_PREFIX}%"}
    await session.execute(
        text(
            "DELETE FROM evaluations WHERE curriculum_id IN "
            "(SELECT id FROM curricula WHERE bucket_key LIKE :pattern)"
        ),
        pattern,
    )
    await session.execute(
        text("DELETE FROM curricula WHERE bucket_key LIKE :pattern"),
        pattern,
    )
    await session.commit()


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Sessão assíncrona contra o banco migrado, com limpeza no teardown.

    Os testes commitam de verdade em vez de rodar dentro de uma transação
    revertida: `now()` do PostgreSQL é o instante da transação, então sem
    commit o `updated_at` jamais avançaria (CA-03-08). O preço é a limpeza
    explícita.

    O `engine.dispose()` ao final descarta o pool: o `engine` é criado no
    import do módulo (RT-02-05) e o pytest-asyncio dá um event loop novo a cada
    teste — reaproveitar uma conexão presa ao loop anterior quebra o teste
    seguinte.
    """
    async with async_session_factory() as active:
        try:
            yield active
        finally:
            # Um teste que provocou erro de banco deixa a transação abortada;
            # sem o rollback, a limpeza não roda.
            await active.rollback()
            await _purge(active)
    await engine.dispose()
