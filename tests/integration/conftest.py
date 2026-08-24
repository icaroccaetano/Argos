"""Fixtures da camada de integração: banco de teste dedicado e sessão.

Os testes desta camada atravessam fronteiras — roteamento, injeção de
dependência, PostgreSQL real. Os de modelo verificam comportamento que só
existe no banco (ENUM nativo, `JSONB`, `CHECK`, `FOREIGN KEY`, defaults de
servidor), então rodam contra o schema migrado pelo Alembic.

O alvo nunca é o banco da aplicação: a suíte opera sobre `POSTGRES_TEST_DB`,
criado e migrado aqui mesmo quando ausente (spec 07 §3.4).

Implementa: RF-07-06, RF-07-07, RN-07-05, RN-07-06, RN-07-07, RN-07-08,
RT-07-06, RT-07-07
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.core.config import settings

# `%(here)s` no `script_location` do `alembic.ini` resolve o caminho das
# migrations a partir do próprio arquivo, o que torna a chamada independente
# do diretório de trabalho (RT-07-07).
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

# `CREATE DATABASE` não pode ser emitido a partir do banco que se quer criar.
MAINTENANCE_DATABASE = "postgres"


def _reject_application_database() -> None:
    """Recusa a execução se o alvo for o banco da aplicação (RN-07-07).

    Primeiro passo da preparação, antes de qualquer comando destrutivo: não
    adianta proteger o `TRUNCATE` se a migration já rodou no banco errado.
    """
    if settings.POSTGRES_TEST_DB == settings.POSTGRES_DB:
        raise RuntimeError(
            f"POSTGRES_TEST_DB aponta para o banco da aplicacao "
            f"('{settings.POSTGRES_DB}'). A suite de integracao trunca tabelas "
            f"a cada teste; alvo recusado."
        )


def _create_test_database() -> None:
    """Cria `POSTGRES_TEST_DB` se ele ainda não existir (RF-07-07).

    A conexão é síncrona e em `AUTOCOMMIT`: no PostgreSQL, `CREATE DATABASE`
    não roda dentro de bloco transacional (RT-07-06).
    """
    url = make_url(settings.database_url_test_sync)
    maintenance = create_engine(
        url.set(database=MAINTENANCE_DATABASE),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with maintenance.connect() as connection:
            already_exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar_one_or_none()
            if already_exists is None:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        maintenance.dispose()


def _migrate_test_database() -> None:
    """Aplica `alembic upgrade head` sobre o banco de teste (RT-07-07).

    A URL definida aqui prevalece sobre a do `Settings` em `migrations/env.py`
    (RF-02-06). O `%` é escapado porque o configparser o interpola.
    """
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", settings.database_url_test_sync.replace("%", "%%")
    )
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> None:
    """Prepara o banco de teste uma vez por invocação do `pytest`.

    Síncrona por decisão: RT-07-02 proíbe arquivo de configuração, e uma
    fixture assíncrona de escopo de sessão exigiria `loop_scope="session"` do
    `pytest-asyncio`, que só se declara em config.

    O banco não é destruído ao final — remigrar a cada execução custa segundos,
    e um banco persistente é inspecionável depois de uma falha.
    """
    _reject_application_database()
    _create_test_database()
    _migrate_test_database()


async def _truncate(session: AsyncSession) -> None:
    """Esvazia as tabelas entre testes (RN-07-06).

    As duas no mesmo comando: nomeá-las juntas dispensa a ordenação que o
    `ON DELETE RESTRICT` (RN-03-08) imporia. Sem `RESTART IDENTITY`, no-op
    sobre PK `UUID`, e sem `CASCADE`, redundante e perigoso.

    A conferência do banco conectado é a segunda metade de RN-07-07: o que se
    defende é o banco da aplicação, então é contra ele que se compara.
    """
    connected = (await session.execute(text("SELECT current_database()"))).scalar_one()
    if connected != settings.POSTGRES_TEST_DB or connected == settings.POSTGRES_DB:
        raise RuntimeError(
            f"Conexao aberta em '{connected}', que nao e o banco de teste "
            f"('{settings.POSTGRES_TEST_DB}'). TRUNCATE recusado."
        )

    await session.execute(text("TRUNCATE evaluations, curricula"))
    await session.commit()


@pytest_asyncio.fixture
async def session(prepared_database: None) -> AsyncGenerator[AsyncSession, None]:
    """Sessão assíncrona contra o banco de teste migrado, com limpeza ao final.

    O engine é próprio da suíte, construído de `database_url_test_async`:
    importar o da aplicação apontaria os testes para o banco errado (RN-07-08).

    Os testes commitam de verdade em vez de rodar dentro de uma transação
    revertida: `now()` do PostgreSQL é o instante da transação, então sem
    commit o `updated_at` jamais avançaria (CA-03-08). O preço é a limpeza
    explícita.

    Engine por teste, descartado no fim: o `pytest-asyncio` dá um event loop
    novo a cada teste, e uma conexão presa ao loop anterior quebra o seguinte.
    """
    engine = create_async_engine(settings.database_url_test_async, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with factory() as active:
            try:
                yield active
            finally:
                # Um teste que provocou erro de banco deixa a transação
                # abortada; sem o rollback, a limpeza não roda.
                await active.rollback()
                await _truncate(active)
    finally:
        await engine.dispose()
