"""Colunas transversais compartilhadas pelos modelos.

Implementa: RF-03-04, RF-03-05, RT-03-02, RT-03-03, RT-03-08
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """`created_at` e `updated_at` com default do banco (RT-03-03).

    O default é `server_default`, não `default` do Python: inserts feitos fora
    do ORM — migrations, scripts de manutenção — também precisam de valor.
    `onupdate` é do lado da aplicação porque o PostgreSQL só atualizaria a
    coluna via trigger, que não temos.

    `now()` do PostgreSQL é o instante de início da **transação**: dois updates
    na mesma transação produzem o mesmo `updated_at`.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """Remoção lógica: `deleted_at IS NULL` identifica o registro vivo (RN-03-08)."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
