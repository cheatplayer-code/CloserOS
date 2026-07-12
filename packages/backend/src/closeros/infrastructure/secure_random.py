"""Cryptographically secure random-byte adapter."""

from __future__ import annotations

import os


class OsSecureRandom:
    """``os.urandom`` implementation of the :class:`SecureRandom` port."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "OsSecureRandom()"

    def generate_bytes(self, *, size: int) -> bytes:
        if type(size) is not int:
            raise TypeError("size must be an int")

        if size <= 0:
            raise ValueError("size must be greater than zero")

        return os.urandom(size)
