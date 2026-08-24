"""Fonte única de configuração da aplicação.

Nenhum outro módulo lê o ambiente. Todos importam a instância `settings`.

Implementa: RF-01-04, RF-02-01, RF-02-02, RF-02-03, RF-02-04, RF-02-07,
RN-02-01, RN-02-02, RN-02-03, RN-02-04, RN-02-05, RT-02-01, RT-02-02, RT-02-06,
RF-07-06
"""

from enum import StrEnum
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ASYNC_DRIVER = "postgresql+asyncpg"
SYNC_DRIVER = "postgresql+psycopg2"

# Sentinela: é o valor que a validação recusa em produção, não um segredo.
FORBIDDEN_PRODUCTION_SECRET = "changeme"  # noqa: S105


class Environment(StrEnum):
    """Ambientes de execução reconhecidos (RN-02-04: não há fallback)."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Configuração tipada, lida do processo e, se presente, do `.env`.

    Variáveis do processo têm precedência sobre o arquivo (RF-02-02), que é o
    que habilita o override de `POSTGRES_HOST` para execução no host
    (RF-02-07). Nenhuma variável obrigatória tem default (RT-02-06).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Environment
    SECRET_KEY: SecretStr
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    # Banco dedicado da suíte de integração (spec 07 §3.4). Tem default
    # porque um nome de banco de teste não é decisão de operação.
    POSTGRES_TEST_DB: str = "argos_test"
    REDIS_URL: str

    @model_validator(mode="after")
    def _reject_weak_production_secret(self) -> Self:
        """RN-02-03: `SECRET_KEY` vazia ou `changeme` não sobe em produção."""
        if self.APP_ENV is not Environment.PRODUCTION:
            return self

        secret = self.SECRET_KEY.get_secret_value()
        if not secret or secret == FORBIDDEN_PRODUCTION_SECRET:
            raise ValueError(
                "SECRET_KEY must not be empty or "
                f"'{FORBIDDEN_PRODUCTION_SECRET}' when APP_ENV is production"
            )
        return self

    def _database_url(self, driver: str, database: str) -> str:
        """Monta a URL com `URL.create()`, nunca por concatenação (RN-02-01).

        A senha é renderizada em claro porque a string alimenta o
        `create_engine`; por isso este valor nunca deve ser logado.
        """
        url = URL.create(
            drivername=driver,
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=database,
        )
        return url.render_as_string(hide_password=False)

    @property
    def database_url_async(self) -> str:
        """URL da aplicação em runtime (`asyncpg`)."""
        return self._database_url(ASYNC_DRIVER, self.POSTGRES_DB)

    @property
    def database_url_sync(self) -> str:
        """URL das migrations do Alembic (`psycopg2`)."""
        return self._database_url(SYNC_DRIVER, self.POSTGRES_DB)

    @property
    def database_url_test_async(self) -> str:
        """URL do banco dedicado da suíte de integração (spec 07 §3.4).

        Deriva das mesmas `POSTGRES_*` da URL da aplicação, trocando apenas o
        nome do banco.
        """
        return self._database_url(ASYNC_DRIVER, self.POSTGRES_TEST_DB)

    @property
    def database_url_test_sync(self) -> str:
        """URL síncrona do banco de teste: migration e conexão de manutenção."""
        return self._database_url(SYNC_DRIVER, self.POSTGRES_TEST_DB)


settings: Settings = Settings()
