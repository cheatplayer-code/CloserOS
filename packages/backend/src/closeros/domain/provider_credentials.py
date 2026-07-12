"""Secret-bearing value objects for provider credential resolution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SecretBytes:
    """Opaque secret bytes hidden from repr and logs."""

    value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.value) is not bytes or not self.value:
            raise ValueError("value must be non-empty bytes")


__all__ = ["SecretBytes"]
