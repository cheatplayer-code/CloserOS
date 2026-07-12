"""Programmatic Alembic configuration for the authentication migrations.

Building the configuration in code lets both the CLI and the test suite point
Alembic at the packaged migration scripts without depending on the current
working directory.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

MIGRATIONS_PATH = Path(__file__).resolve().parent / "migrations"


def build_alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    return config
