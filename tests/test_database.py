"""Testes de aceite da dependência de sessão.

Implementa: CA-02-10
"""

from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db


def build_probe_app(
    received: list[AsyncSession],
) -> FastAPI:
    """App mínima com duas rotas dependentes de `get_db()`."""
    app = FastAPI()

    @app.get("/probe")
    async def probe(session: AsyncSession = Depends(get_db)) -> dict[str, str]:
        received.append(session)
        return {"type": type(session).__name__}

    @app.get("/probe-failing")
    async def probe_failing(
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, str]:
        received.append(session)
        raise RuntimeError("boom")

    return app


@pytest.fixture
def closed_sessions(monkeypatch: pytest.MonkeyPatch) -> list[AsyncSession]:
    """Registra toda chamada a `AsyncSession.close()`, sem suprimi-la."""
    recorded: list[AsyncSession] = []
    original = AsyncSession.close

    async def spy(self: AsyncSession, *args: Any, **kwargs: Any) -> None:
        recorded.append(self)
        await original(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "close", spy)
    return recorded


def test_ca_02_10_route_receives_async_session(
    closed_sessions: list[AsyncSession],
) -> None:
    received: list[AsyncSession] = []
    client = TestClient(build_probe_app(received))

    response = client.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"type": "AsyncSession"}
    assert len(received) == 1
    assert isinstance(received[0], AsyncSession)
    assert received[0] in closed_sessions


def test_ca_02_10_session_is_closed_when_route_raises(
    closed_sessions: list[AsyncSession],
) -> None:
    received: list[AsyncSession] = []
    client = TestClient(build_probe_app(received), raise_server_exceptions=False)

    response = client.get("/probe-failing")

    assert response.status_code == 500
    assert len(received) == 1
    assert received[0] in closed_sessions
