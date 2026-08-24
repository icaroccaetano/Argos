"""Ambiente do Alembic.

A URL vem do `Settings` (RT-01-01: nenhum módulo lê o ambiente por conta
própria) e o driver síncrono já vem derivado de lá — não há conversão de
string de conexão aqui. Uma URL já presente no `Config` do Alembic tem
precedência sobre ela (RF-02-06).

Implementa: RF-02-06, RT-01-01, RT-01-09, RT-07-07
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from api.core.config import settings
from api.models.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# A URL do `Config` prevalece quando já vier definida (RF-02-06): é ela que
# permite ao chamador programático — a suíte de integração da spec 07
# (RT-07-07) — apontar a migration para outro banco. Pela linha de comando,
# `alembic.ini` traz `sqlalchemy.url` vazia e a URL continua vindo do
# `Settings`.
#
# `%` é o caractere de interpolação do configparser: uma senha que o contenha
# quebraria a leitura da opção se não fosse escapada.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option(
        "sqlalchemy.url", settings.database_url_sync.replace("%", "%%")
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
