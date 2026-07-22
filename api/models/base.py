"""Declarative base compartilhada pelos modelos ORM.

Implementa: RT-01-05, RT-01-09
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa do SQLAlchemy 2.0.

    Todo modelo ORM herda desta classe. `Base.metadata` é o alvo do
    autogenerate do Alembic (`migrations/env.py`).
    """
