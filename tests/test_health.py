"""Testes de aceite do endpoint operacional de saúde.

Implementa: CA-01-02
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_ca_01_02_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
