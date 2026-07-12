"""Framework-independent bounded adapter metadata value object."""

from collections.abc import Mapping
from dataclasses import dataclass

_MAX_ENTRIES = 32
_MAX_KEY_LENGTH = 64
_MAX_STRING_VALUE_LENGTH = 512
_MAX_TOTAL_SERIALIZED_SIZE = 4096

_SENSITIVE_KEY_FRAGMENTS = frozenset(
    {
        "body",
        "text",
        "message",
        "content",
        "token",
        "secret",
        "password",
        "authorization",
        "cookie",
        "email",
        "phone",
        "payload",
    }
)

AdapterScalar = str | int | bool | None


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.strip().lower()

    if not normalized_key:
        return True

    return any(fragment in normalized_key for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _validate_scalar_value(value: object, key: str) -> AdapterScalar:
    if value is None:
        return None

    if type(value) is str:
        if not value:
            raise ValueError(f"adapter metadata value for '{key}' must not be empty")

        if len(value) > _MAX_STRING_VALUE_LENGTH:
            raise ValueError(
                f"adapter metadata value for '{key}' exceeds {_MAX_STRING_VALUE_LENGTH} characters"
            )

        return value

    if type(value) is int:
        return value

    if type(value) is bool:
        return value

    raise ValueError(f"adapter metadata value for '{key}' must be a JSON scalar")


def _estimate_serialized_size(entries: Mapping[str, AdapterScalar]) -> int:
    size = 2

    for index, (key, value) in enumerate(entries.items()):
        if index > 0:
            size += 1

        size += len(key) + 2

        if value is None:
            size += 4
        elif type(value) is bool:
            size += 4 if value else 5
        elif type(value) is int:
            size += len(str(value))
        elif type(value) is str:
            size += len(value) + 2

    return size


def _normalize_adapter_metadata(values: Mapping[str, object] | None) -> dict[str, AdapterScalar]:
    if values is None:
        return {}

    if not isinstance(values, Mapping):
        raise TypeError("adapter metadata must be a mapping")

    if len(values) > _MAX_ENTRIES:
        raise ValueError(f"adapter metadata must contain at most {_MAX_ENTRIES} entries")

    normalized: dict[str, AdapterScalar] = {}

    for raw_key, raw_value in values.items():
        if not isinstance(raw_key, str):
            raise TypeError("adapter metadata keys must be strings")

        key = raw_key.strip()

        if not key:
            raise ValueError("adapter metadata keys must not be empty")

        if len(key) > _MAX_KEY_LENGTH:
            raise ValueError(f"adapter metadata key '{key}' exceeds {_MAX_KEY_LENGTH} characters")

        if _is_sensitive_key(key):
            raise ValueError(f"adapter metadata key '{key}' is not allowed")

        if key in normalized:
            raise ValueError(f"adapter metadata key '{key}' is duplicated")

        normalized[key] = _validate_scalar_value(raw_value, key)

    if _estimate_serialized_size(normalized) > _MAX_TOTAL_SERIALIZED_SIZE:
        raise ValueError(f"adapter metadata exceeds {_MAX_TOTAL_SERIALIZED_SIZE} serialized bytes")

    return normalized


@dataclass(frozen=True, slots=True)
class AdapterMetadata:
    entries: tuple[tuple[str, AdapterScalar], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")

        seen_keys: set[str] = set()

        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError("entries must contain (key, value) tuples")

            key, value = entry

            if not isinstance(key, str):
                raise TypeError("adapter metadata keys must be strings")

            if key in seen_keys:
                raise ValueError(f"adapter metadata key '{key}' is duplicated")

            seen_keys.add(key)
            _validate_scalar_value(value, key)

        serialized = dict(self.entries)

        if len(serialized) > _MAX_ENTRIES:
            raise ValueError(f"adapter metadata must contain at most {_MAX_ENTRIES} entries")

        if _estimate_serialized_size(serialized) > _MAX_TOTAL_SERIALIZED_SIZE:
            raise ValueError(
                f"adapter metadata exceeds {_MAX_TOTAL_SERIALIZED_SIZE} serialized bytes"
            )

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None = None) -> "AdapterMetadata":
        normalized = _normalize_adapter_metadata(values)
        return cls(entries=tuple(sorted(normalized.items())))

    def as_dict(self) -> dict[str, AdapterScalar]:
        return dict(self.entries)

    @property
    def is_empty(self) -> bool:
        return not self.entries
