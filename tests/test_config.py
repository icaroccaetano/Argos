"""Testes de aceite do módulo de configuração.

Implementa: CA-02-04, CA-02-05, CA-02-06, CA-02-07
"""

from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import make_url

from api.core.config import Settings, settings

VALID_ENV: dict[str, Any] = {
    "APP_ENV": "development",
    "SECRET_KEY": "s3cr3t",
    "POSTGRES_USER": "argos",
    "POSTGRES_PASSWORD": "argos",
    "POSTGRES_DB": "argos",
    "POSTGRES_HOST": "db",
    "REDIS_URL": "redis://redis:6379/0",
}


def build_settings(**overrides: Any) -> Settings:
    """Instancia `Settings` isolada do `.env` e do ambiente do processo."""
    values = {**VALID_ENV, **overrides}
    return Settings(_env_file=None, **values)


def test_ca_02_04_password_with_special_chars_does_not_corrupt_host() -> None:
    configured = build_settings(POSTGRES_PASSWORD="p@ss:w/rd#1")

    for raw_url in (configured.database_url_async, configured.database_url_sync):
        url = make_url(raw_url)

        assert url.host == "db"
        assert url.password == "p@ss:w/rd#1"
        assert url.database == "argos"


def test_ca_02_05_missing_required_variable_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # O ambiente do container define `POSTGRES_DB`; a ausência precisa ser
    # simulada também no processo, não apenas nos valores passados.
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    values = {k: v for k, v in VALID_ENV.items() if k != "POSTGRES_DB"}

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **values)

    assert "POSTGRES_DB" in str(excinfo.value)


def test_ca_02_06_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(APP_ENV="staging")


def test_ca_02_06_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError):
        build_settings(APP_ENV="production", SECRET_KEY="changeme")

    with pytest.raises(ValidationError):
        build_settings(APP_ENV="production", SECRET_KEY="")


def test_ca_02_07_repr_hides_secrets() -> None:
    # Valores sentinela: o `.env` de desenvolvimento usa `argos` como senha e
    # também como usuário e banco, o que tornaria a asserção ambígua.
    configured = build_settings(
        SECRET_KEY="secret-sentinel-value",
        POSTGRES_PASSWORD="password-sentinel-value",
    )

    rendered = repr(configured)

    assert "secret-sentinel-value" not in rendered
    assert "password-sentinel-value" not in rendered
    assert "**********" in rendered
    # A instância de módulo usa a mesma classe e o mesmo mascaramento.
    assert "**********" in repr(settings)
