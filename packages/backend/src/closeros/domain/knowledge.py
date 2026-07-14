"""Framework-independent knowledge-base domain types (Block NOPQ)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

SOURCE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
KNOWLEDGE_DOCUMENT_MAX_BYTES = 5 * 1024 * 1024
KNOWLEDGE_CHUNK_MAX_BYTES = 32 * 1024
CHUNK_MAX_CHARACTERS = 2000
CHUNK_OVERLAP_CHARACTERS = 200
SEARCH_KEY_VERSION = "v1-unicode-search-v1"
TERM_DIGEST_SIZE_BYTES = 32


class KnowledgeDocumentKind(StrEnum):
    PRICE_LIST = "price_list"
    SERVICE_CATALOG = "service_catalog"
    FAQ = "faq"
    SALES_SCRIPT = "sales_script"
    PROMOTION = "promotion"
    POLICY = "policy"
    PROHIBITED_CLAIMS = "prohibited_claims"
    GENERAL_REFERENCE = "general_reference"


class KnowledgeDocumentStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    INDEXED = "indexed"
    REVOKED = "revoked"
    EXPIRED = "expired"
    FAILED = "failed"


class KnowledgeVersionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    INDEXED = "indexed"
    REVOKED = "revoked"
    EXPIRED = "expired"
    FAILED = "failed"


def _validate_uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _validate_timezone_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_source_code(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not SOURCE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must match the controlled source_code pattern")
    return normalized


def _validate_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _validate_term_digest(value: object, field_name: str) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{field_name} must be bytes")
    if len(value) != TERM_DIGEST_SIZE_BYTES:
        raise ValueError(f"{field_name} must contain exactly {TERM_DIGEST_SIZE_BYTES} bytes")
    return value


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: UUID
    tenant_id: UUID
    source_code: str
    kind: KnowledgeDocumentKind
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self, "source_code", _validate_source_code(self.source_code, "source_code")
        )
        if not isinstance(self.kind, KnowledgeDocumentKind):
            raise TypeError("kind must be a KnowledgeDocumentKind")
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentVersion:
    id: UUID
    tenant_id: UUID
    document_id: UUID
    version_number: int
    source_content_id: UUID
    effective_from: datetime
    effective_until: datetime | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    status: KnowledgeVersionStatus
    indexed_at: datetime | None
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "document_id", _validate_uuid(self.document_id, "document_id"))
        object.__setattr__(
            self, "version_number", _validate_positive_int(self.version_number, "version_number")
        )
        object.__setattr__(
            self, "source_content_id", _validate_uuid(self.source_content_id, "source_content_id")
        )
        object.__setattr__(
            self,
            "effective_from",
            _validate_timezone_aware_datetime(self.effective_from, "effective_from"),
        )
        if self.effective_until is not None:
            object.__setattr__(
                self,
                "effective_until",
                _validate_timezone_aware_datetime(self.effective_until, "effective_until"),
            )
            if self.effective_until <= self.effective_from:
                raise ValueError("effective_until must be later than effective_from")
        if self.approved_by_user_id is not None:
            object.__setattr__(
                self,
                "approved_by_user_id",
                _validate_uuid(self.approved_by_user_id, "approved_by_user_id"),
            )
        if self.approved_at is not None:
            object.__setattr__(
                self,
                "approved_at",
                _validate_timezone_aware_datetime(self.approved_at, "approved_at"),
            )
        if not isinstance(self.status, KnowledgeVersionStatus):
            raise TypeError("status must be a KnowledgeVersionStatus")
        if self.indexed_at is not None:
            object.__setattr__(
                self, "indexed_at", _validate_timezone_aware_datetime(self.indexed_at, "indexed_at")
            )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: UUID
    tenant_id: UUID
    document_version_id: UUID
    ordinal: int
    content_id: UUID
    plaintext_hash: bytes
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _validate_uuid(self.id, "id"))
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "document_version_id",
            _validate_uuid(self.document_version_id, "document_version_id"),
        )
        object.__setattr__(self, "ordinal", _validate_positive_int(self.ordinal, "ordinal"))
        object.__setattr__(self, "content_id", _validate_uuid(self.content_id, "content_id"))
        object.__setattr__(
            self, "plaintext_hash", _validate_term_digest(self.plaintext_hash, "plaintext_hash")
        )
        object.__setattr__(
            self, "created_at", _validate_timezone_aware_datetime(self.created_at, "created_at")
        )


@dataclass(frozen=True, slots=True)
class KnowledgeChunkTerm:
    tenant_id: UUID
    chunk_id: UUID
    term_digest: bytes
    weight: int
    search_key_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _validate_uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "chunk_id", _validate_uuid(self.chunk_id, "chunk_id"))
        object.__setattr__(
            self, "term_digest", _validate_term_digest(self.term_digest, "term_digest")
        )
        if type(self.weight) is not int or self.weight < 1:
            raise ValueError("weight must be a positive integer")
        if type(self.search_key_version) is not str or not self.search_key_version.strip():
            raise ValueError("search_key_version must be a non-empty string")


@dataclass(frozen=True, slots=True)
class KnowledgeCitation:
    chunk_id: UUID
    source_code: str
    version_number: int
    document_kind: KnowledgeDocumentKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", _validate_uuid(self.chunk_id, "chunk_id"))
        object.__setattr__(
            self, "source_code", _validate_source_code(self.source_code, "source_code")
        )
        object.__setattr__(
            self, "version_number", _validate_positive_int(self.version_number, "version_number")
        )
        if not isinstance(self.document_kind, KnowledgeDocumentKind):
            raise TypeError("document_kind must be a KnowledgeDocumentKind")


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalResult:
    chunk_id: UUID
    source_code: str
    version_number: int
    document_kind: KnowledgeDocumentKind
    match_weight: int
    decrypted_text: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", _validate_uuid(self.chunk_id, "chunk_id"))
        object.__setattr__(
            self, "source_code", _validate_source_code(self.source_code, "source_code")
        )
        object.__setattr__(
            self, "version_number", _validate_positive_int(self.version_number, "version_number")
        )
        if not isinstance(self.document_kind, KnowledgeDocumentKind):
            raise TypeError("document_kind must be a KnowledgeDocumentKind")
        if type(self.match_weight) is not int or self.match_weight < 1:
            raise ValueError("match_weight must be a positive integer")
        if type(self.decrypted_text) is not str:
            raise TypeError("decrypted_text must be a string")

    def __repr__(self) -> str:
        return (
            "KnowledgeRetrievalResult("
            f"chunk_id={self.chunk_id!s}, "
            f"source_code={self.source_code!r}, "
            f"version_number={self.version_number}, "
            f"document_kind={self.document_kind.value!r}, "
            f"match_weight={self.match_weight}, "
            "decrypted_text='[REDACTED]')"
        )
