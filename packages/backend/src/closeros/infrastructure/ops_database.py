"""Database helpers for operator scripts."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from closeros.application.integrated_unit_of_work import IntegratedUnitOfWork
from closeros.infrastructure.database import create_async_engine, create_session_factory
from closeros.infrastructure.integrated_unit_of_work import SqlAlchemyIntegratedUnitOfWork


def build_integrated_uow_factory(
    database_url: str,
) -> Callable[[], IntegratedUnitOfWork]:
    engine = create_async_engine(database_url)
    session_factory = create_session_factory(engine)

    def factory() -> IntegratedUnitOfWork:
        return cast(IntegratedUnitOfWork, SqlAlchemyIntegratedUnitOfWork(session_factory))

    return factory
