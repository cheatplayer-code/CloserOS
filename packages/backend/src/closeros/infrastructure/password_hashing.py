"""Argon2id password hashing adapter.

Implements the application :class:`PasswordHasher` port using the maintained
``argon2-cffi`` library. No custom cryptography is implemented here.

The adapter never places plaintext passwords or PHC hash strings in its
``repr`` or in any exception message.
"""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2PasswordHasher
from argon2 import Type as _Argon2Type
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from closeros.application.password_hashing import PasswordVerification
from closeros.domain.authentication import PasswordHash

# ADR-0010 minimum Argon2id parameters. Memory cost is expressed in kibibytes,
# so 19 MiB is 19 * 1024 = 19456 KiB.
_MEMORY_COST_KIB = 19 * 1024
_TIME_COST = 2
_PARALLELISM = 1


class Argon2idPasswordHasher:
    """Argon2id implementation of the password hashing port."""

    __slots__ = ("_hasher",)

    def __init__(
        self,
        *,
        memory_cost_kib: int = _MEMORY_COST_KIB,
        time_cost: int = _TIME_COST,
        parallelism: int = _PARALLELISM,
    ) -> None:
        self._hasher = _Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            type=_Argon2Type.ID,
        )

    def __repr__(self) -> str:
        return "Argon2idPasswordHasher()"

    def hash_password(self, plaintext: str) -> PasswordHash:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be a string")

        if not plaintext:
            raise ValueError("plaintext must not be empty")

        encoded = self._hasher.hash(plaintext)
        return PasswordHash(encoded=encoded)

    def verify_password(
        self,
        *,
        candidate: str,
        stored: PasswordHash,
    ) -> PasswordVerification:
        if not isinstance(candidate, str):
            raise TypeError("candidate must be a string")

        if not isinstance(stored, PasswordHash):
            raise TypeError("stored must be a PasswordHash")

        try:
            self._hasher.verify(stored.encoded, candidate)
        except VerifyMismatchError:
            return PasswordVerification(is_valid=False, requires_rehash=False)
        except (InvalidHashError, VerificationError):
            return PasswordVerification(is_valid=False, requires_rehash=False)

        try:
            requires_rehash = self._hasher.check_needs_rehash(stored.encoded)
        except (InvalidHashError, VerificationError):
            requires_rehash = True

        return PasswordVerification(is_valid=True, requires_rehash=requires_rehash)
