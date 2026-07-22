"""Engine assíncrono, fábrica de sessões e dependência de sessão.

Implementa: RF-02-05, RT-01-07, RT-02-03, RT-02-05
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url_async,
    pool_pre_ping=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Entrega uma sessão por requisição e a encerra ao final.

    O `async with` fecha a sessão inclusive quando a requisição levanta
    exceção. Não há `commit()` implícito: a transação é responsabilidade do
    serviço (RT-02-03).
    """
    async with async_session_factory() as session:
        yield session
