"""Application-facing password hashing port.

This module defines the framework-independent contract for password hashing.
It must not import any concrete cryptography library. The infrastructure layer
provides the Argon2id implementation.
"""

from dataclasses import dataclass
from typing import Protocol

from closeros.domain.authentication import PasswordHash


@dataclass(frozen=True, slots=True)
class PasswordVerification:
    """Result of verifying a candidate password against a stored hash.

    `is_valid` reports whether the candidate matched. `requires_rehash` reports
    whether a successful match was produced by a stored hash whose parameters are
    below current policy and should be replaced. `requires_rehash` is only
    meaningful when `is_valid` is `True`.
    """

    is_valid: bool
    requires_rehash: bool


class PasswordHasher(Protocol):
    """Port for hashing and verifying passwords."""

    def hash_password(self, plaintext: str) -> PasswordHash: ...

    def verify_password(
        self,
        *,
        candidate: str,
        stored: PasswordHash,
    ) -> PasswordVerification: ...
