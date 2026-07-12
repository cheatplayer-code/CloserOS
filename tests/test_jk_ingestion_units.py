"""Unit tests for JK ingestion adapters, schemas, and queue helpers."""

# mypy: disable-error-code=var-annotated

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from closeros.application.provider_adapter_registry import (
    DuplicateProviderAdapterError,
    ProviderAdapterRegistry,
    UnknownProviderAdapterError,
)
from closeros.domain.canonical_enums import ProviderKind
from closeros.domain.csv_import import CsvColumnMapping, CsvDelimiter, CsvSourceEncoding
from closeros.infrastructure.redis_stream_queue import (
    _extract_xautoclaim_messages,
    _extract_xreadgroup_messages,
    _parse_job_id,
)
from closeros.infrastructure.synthetic_hmac_adapter import (
    SyntheticHmacWebhookAdapter,
    build_synthetic_signature,
)

from tests.ingestion_support import (
    SYNTHETIC_WEBHOOK_SECRET,
    build_synthetic_message_received_payload,
    build_synthetic_webhook_headers,
    default_csv_mapping,
    sample_csv_bytes,
)


@pytest.mark.parametrize(
    "provider",
    ["synthetic", "whatsapp", "instagram", "telegram_business"],
)
def test_provider_kind_values_are_lowercase(provider: str) -> None:
    assert ProviderKind(provider).value == provider


def test_synthetic_signature_is_stable() -> None:
    body = b'{"event":"test"}'
    first = build_synthetic_signature(secret=SYNTHETIC_WEBHOOK_SECRET, body=body)
    second = build_synthetic_signature(secret=SYNTHETIC_WEBHOOK_SECRET, body=body)
    assert first == second
    assert first != build_synthetic_signature(secret=b"other-secret-value-32-bytes!!", body=body)


def test_synthetic_adapter_verifies_valid_webhook() -> None:
    async def exercise() -> None:
        adapter = SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        verified = await adapter.verify_webhook(
            raw_body=body,
            headers=headers,
            connection_id=uuid4(),
            tenant_id=uuid4(),
        )
        assert verified.external_event_id
        assert verified.raw_body == body

    import asyncio

    asyncio.run(exercise())


def test_synthetic_adapter_rejects_bad_signature() -> None:
    async def exercise() -> None:
        from closeros.application.provider_ports import ProviderSignatureError

        adapter = SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        headers["x-synthetic-signature"] = "bad"
        with pytest.raises(ProviderSignatureError):
            await adapter.verify_webhook(
                raw_body=body,
                headers=headers,
                connection_id=uuid4(),
                tenant_id=uuid4(),
            )

    import asyncio

    asyncio.run(exercise())


def test_synthetic_adapter_normalizes_message_received() -> None:
    adapter = SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET)
    payload = build_synthetic_message_received_payload()
    operations = adapter.normalize_payload(
        decrypted_payload=payload,
        content_type="application/json",
    )
    assert len(operations) == 1
    assert operations[0].external_message_id == "msg-synthetic-001"


def test_provider_adapter_registry_resolves_synthetic() -> None:
    adapter = SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET)
    registry = ProviderAdapterRegistry(adapters=(adapter,))
    resolved = registry.resolve(ProviderKind.SYNTHETIC)
    assert resolved.provider_kind is ProviderKind.SYNTHETIC


def test_provider_adapter_registry_rejects_duplicate_registration() -> None:
    adapter = SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET)
    registry = ProviderAdapterRegistry()
    registry.register(adapter)
    with pytest.raises(DuplicateProviderAdapterError):
        registry.register(adapter)


def test_provider_adapter_registry_unknown_provider() -> None:
    registry = ProviderAdapterRegistry(
        adapters=(SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET),),
    )
    with pytest.raises(UnknownProviderAdapterError):
        registry.resolve(ProviderKind.WHATSAPP)


@pytest.mark.parametrize(
    ("field_indexes", "should_fail"),
    [
        (default_csv_mapping(), False),
        ({"external_conversation_id": 0}, True),
        ({**default_csv_mapping(), "unknown_field": 0}, True),
    ],
)
def test_csv_column_mapping_validation(field_indexes: dict[str, int], should_fail: bool) -> None:
    if should_fail:
        with pytest.raises(ValueError):
            CsvColumnMapping.from_dict(field_indexes)
    else:
        mapping = CsvColumnMapping.from_dict(field_indexes)
        assert mapping.as_dict()["message_text"] == 6


@pytest.mark.parametrize(
    "delimiter",
    [CsvDelimiter.COMMA, CsvDelimiter.SEMICOLON, CsvDelimiter.TAB],
)
def test_csv_delimiter_enum_values(delimiter: CsvDelimiter) -> None:
    assert delimiter.value in {"comma", "semicolon", "tab"}


@pytest.mark.parametrize(
    "encoding",
    [CsvSourceEncoding.UTF8, CsvSourceEncoding.UTF8_BOM],
)
def test_csv_source_encoding_enum_values(encoding: CsvSourceEncoding) -> None:
    assert encoding.value in {"utf8", "utf8_bom"}


def test_sample_csv_bytes_has_header_and_row() -> None:
    text = sample_csv_bytes().decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 2
    assert "external_message_id" in lines[0]


def test_parse_job_id_from_stream_fields() -> None:
    job_id = uuid4()
    parsed = _parse_job_id({"job_id": str(job_id)})
    assert parsed == job_id


def test_parse_job_id_rejects_invalid_uuid() -> None:
    assert _parse_job_id({"job_id": "not-a-uuid"}) is None
    assert _parse_job_id({"other": "value"}) is None
    assert _parse_job_id(None) is None


def test_extract_messages_empty_response() -> None:
    assert _extract_xautoclaim_messages(None) == ()
    assert _extract_xreadgroup_messages([]) == ()
    assert _extract_xreadgroup_messages(()) == ()


def test_extract_messages_from_xreadgroup_shape() -> None:
    job_id = UUID("00000000-0000-0000-0000-000000000001")
    response = [
        [
            b"stream",
            [
                (b"1700000000000-0", {b"job_id": str(job_id).encode("ascii")}),
            ],
        ]
    ]
    messages = _extract_xreadgroup_messages(response)
    assert messages == (("1700000000000-0", job_id),)


def test_synthetic_webhook_headers_include_content_type() -> None:
    body = json.dumps({"operations": []}).encode("utf-8")
    headers = build_synthetic_webhook_headers(body=body)
    assert headers["content-type"] == "application/json"
    assert headers["x-synthetic-event-id"]


def test_synthetic_payload_uses_timezone_aware_timestamps() -> None:
    payload = json.loads(build_synthetic_message_received_payload().decode("utf-8"))
    sent_at = datetime.fromisoformat(payload["operations"][0]["sent_at"])
    assert sent_at.tzinfo is not None


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        ("synthetic", ProviderKind.SYNTHETIC),
        ("whatsapp", ProviderKind.WHATSAPP),
        ("instagram", ProviderKind.INSTAGRAM),
        ("telegram_business", ProviderKind.TELEGRAM_BUSINESS),
    ],
)
def test_provider_kind_parsing(raw_value: str, expected: ProviderKind) -> None:
    assert ProviderKind(raw_value) is expected


@pytest.mark.parametrize("invalid", ["", "unknown", "SYNTHETIC", "meta"])
def test_provider_kind_rejects_invalid_values(invalid: str) -> None:
    with pytest.raises(ValueError):
        ProviderKind(invalid)


@pytest.mark.parametrize(
    "secret",
    [
        SYNTHETIC_WEBHOOK_SECRET,
        b"synthetic-secret-for-tests-32b!",
        bytes(range(32)),
    ],
)
def test_build_synthetic_signature_accepts_32_byte_secrets(secret: bytes) -> None:
    signature = build_synthetic_signature(secret=secret, body=b"payload")
    assert len(signature) == 64


def test_build_synthetic_signature_changes_with_body() -> None:
    secret = SYNTHETIC_WEBHOOK_SECRET
    assert build_synthetic_signature(secret=secret, body=b"a") != build_synthetic_signature(
        secret=secret,
        body=b"b",
    )


@pytest.mark.parametrize(
    "headers_missing",
    [
        "x-synthetic-signature",
        "x-synthetic-event-id",
    ],
)
def test_synthetic_adapter_requires_headers(headers_missing: str) -> None:
    async def exercise() -> None:
        from closeros.application.provider_ports import ProviderSignatureError

        adapter = SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET)
        body = build_synthetic_message_received_payload()
        headers = build_synthetic_webhook_headers(body=body)
        del headers[headers_missing]
        with pytest.raises(ProviderSignatureError):
            await adapter.verify_webhook(
                raw_body=body,
                headers=headers,
                connection_id=uuid4(),
                tenant_id=uuid4(),
            )

    import asyncio

    asyncio.run(exercise())


def test_synthetic_adapter_provider_kind_property() -> None:
    adapter = SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET)
    assert adapter.provider_kind is ProviderKind.SYNTHETIC


def test_provider_registry_registered_kinds() -> None:
    registry = ProviderAdapterRegistry(
        adapters=(SyntheticHmacWebhookAdapter(secret=SYNTHETIC_WEBHOOK_SECRET),),
    )
    assert registry.registered_kinds() == frozenset({ProviderKind.SYNTHETIC})


@pytest.mark.parametrize(
    "fields",
    [
        {
            "external_conversation_id": 0,
            "external_message_id": 1,
            "sender_type": 2,
            "direction": 3,
            "sent_at": 4,
            "received_at": 5,
            "message_text": 6,
        },
        {**default_csv_mapping(), "reply_to_external_message_id": 7},
    ],
)
def test_csv_mapping_accepts_valid_shapes(fields: dict[str, int]) -> None:
    mapping = CsvColumnMapping.from_dict(fields)
    assert mapping.as_dict()


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {
            "external_conversation_id": -1,
            "external_message_id": 1,
            "sender_type": 2,
            "direction": 3,
            "sent_at": 4,
            "received_at": 5,
            "message_text": 6,
        },
    ],
)
def test_csv_mapping_rejects_invalid_shapes(fields: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        CsvColumnMapping.from_dict(fields)


def test_parse_job_id_accepts_bytes_job_id() -> None:
    job_id = uuid4()
    parsed = _parse_job_id({b"job_id": str(job_id).encode("ascii")})
    assert parsed == job_id


@pytest.mark.parametrize(
    "payload",
    [
        {"job_id": 123},
        {"job_id": ""},
        {"job_id": "   "},
        "not-a-dict",
    ],
)
def test_parse_job_id_rejects_invalid_payloads(payload: object) -> None:
    assert _parse_job_id(payload) is None


def test_extract_messages_from_autoclaim_shape() -> None:
    job_id = UUID("00000000-0000-0000-0000-000000000002")
    response = (
        b"0-0",
        [(b"1700000000001-0", {b"job_id": str(job_id).encode("ascii")})],
        [],
    )
    messages = _extract_xautoclaim_messages(response)
    assert messages == (("1700000000001-0", job_id),)


def test_ingestion_support_default_mapping_has_required_fields() -> None:
    mapping = default_csv_mapping()
    required = {
        "external_conversation_id",
        "external_message_id",
        "sender_type",
        "direction",
        "sent_at",
        "received_at",
        "message_text",
    }
    assert required.issubset(mapping.keys())


def test_worker_settings_defaults_development_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    from closeros_worker.settings import WorkerSettings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    settings = WorkerSettings.from_env()
    assert settings.database_url
    assert settings.redis_url
    assert settings.outbox_stream == "closeros.outbox.jobs"


def test_api_settings_ingestion_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from closeros_api.settings import ApiSettings

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/local@127.0.0.1:5432/local")
    settings = ApiSettings.from_env()
    assert settings.webhook_max_body_bytes == 1_048_576
    assert settings.csv_max_body_bytes == 10_485_760
    assert settings.ingestion_service_id


def test_production_api_settings_require_ingestion_service_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from closeros_api.settings import ApiConfigurationError, ApiSettings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/local@127.0.0.1:5432/local")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "https://app.example.test")
    monkeypatch.setenv("AUTH_CSRF_SECRET", "production_csrf_secret_32_chars_xx")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SECRET", "production_rate_secret_32_chars_xx")
    monkeypatch.delenv("INGESTION_SERVICE_ID", raising=False)
    with pytest.raises(ApiConfigurationError):
        ApiSettings.from_env()


def test_jk_supported_job_kinds_include_ingestion() -> None:
    from closeros.domain.outbox import OutboxJobKind
    from closeros_worker.runtime import LM_SUPPORTED_JOB_KINDS

    assert OutboxJobKind.WEBHOOK_NORMALIZE in LM_SUPPORTED_JOB_KINDS
    assert OutboxJobKind.CSV_IMPORT in LM_SUPPORTED_JOB_KINDS


def test_csv_import_schemas_forbid_extra_fields() -> None:
    from closeros_api.csv_import_schemas import CsvImportStartRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CsvImportStartRequest.model_validate({"mapping": {"message_text": 1}, "extra": True})


def test_csv_import_preview_response_shape() -> None:
    from closeros_api.csv_import_schemas import CsvImportPreviewResponse

    payload = CsvImportPreviewResponse.model_validate(
        {
            "import_id": "00000000-0000-0000-0000-000000000001",
            "columns": [{"index": 0, "label": "message_text"}],
            "total_rows": 1,
        }
    )
    assert payload.total_rows == 1
