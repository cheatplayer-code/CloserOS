"""Infrastructure adapters for persistence, cryptography, and migrations."""

from closeros.infrastructure.authentication_unit_of_work import (
    SqlAlchemyAuthenticationUnitOfWork,
)
from closeros.infrastructure.database import (
    DatabaseConfigurationError,
    create_authentication_engine,
    create_authentication_sessionmaker,
    create_migration_engine,
    database_url_from_env,
    normalize_database_url,
)
from closeros.infrastructure.password_hashing import Argon2idPasswordHasher

__all__ = [
    "Argon2idPasswordHasher",
    "DatabaseConfigurationError",
    "SqlAlchemyAuthenticationUnitOfWork",
    "create_authentication_engine",
    "create_authentication_sessionmaker",
    "create_migration_engine",
    "database_url_from_env",
    "normalize_database_url",
]
