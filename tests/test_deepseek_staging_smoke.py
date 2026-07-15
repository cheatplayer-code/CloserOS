"""HTTP transport tests for the S2 DeepSeek staging smoke."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from closeros_api.auth_security import CSRF_HEADER_NAME

from scripts.ops.deepseek_staging_smoke import SmokeFailure, run_smoke

TENANT_ID = "41a9f40e-f70e-46f3-b70f-88775cdd9ca0"
THREAD_ID = "1ef12b18-f3f0-4815-a7bf-e9951411a5c8"
RUN_ID = "80692d2c-1fd8-466d-9338-4bb9ec6a0398"
CANDIDATE_ID = "a4216c7d-0b53-4172-bab6-1d7bf0c9fc89"
DRAFT_ID = "fd0255f9-75e2-4f70-814c-16854ef262c1"


def _response(payload: object, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _live_run() -> dict[str, object]:
    return {
        "id": RUN_ID,
        "conversation_thread_id": THREAD_ID,
        "status": "completed",
        "provider_code": "openai",
        "model_code": "deepseek-v4-flash",
        "input_tokens": 132,
        "output_tokens": 51,
        "latency_milliseconds": 812,
        "cost_status": "unknown",
        "estimated_cost_microunits": None,
        "failure_code": None,
        "candidates": [
            {
                "id": CANDIDATE_ID,
                "evidence_message_ids": [str(uuid4())],
            }
        ],
    }


def _common_handler(request: httpx.Request) -> httpx.Response | None:
    path = request.url.path
    if request.method == "GET" and path == "/health":
        return _response({"status": "ok"})
    if request.method == "GET" and path == "/ready":
        return _response({"status": "ready", "dependencies": {"database": "ok"}})
    if request.method == "POST" and path == "/api/v1/auth/login":
        return _response({"csrf_token": "csrf-for-smoke"})
    if request.method == "GET" and path == "/api/v1/tenants":
        return _response([{"id": TENANT_ID, "time_zone": "Asia/Almaty"}])
    if request.method == "GET" and path == f"/api/v1/tenants/{TENANT_ID}/conversations":
        return _response({"conversations": [{"id": THREAD_ID}]})
    if request.method == "POST" and path == "/api/v1/auth/logout":
        return httpx.Response(204)
    return None


def test_live_smoke_verifies_actual_metadata_and_draft_creation() -> None:
    live_run = _live_run()

    def handler(request: httpx.Request) -> httpx.Response:
        common = _common_handler(request)
        if common is not None:
            return common
        path = request.url.path
        if request.method == "POST" and path.endswith("/reply-suggestions"):
            assert request.headers[CSRF_HEADER_NAME] == "csrf-for-smoke"
            assert request.headers["origin"] == "https://web-staging.example.com"
            assert request.headers["idempotency-key"].startswith("s2-deepseek-smoke-")
            return _response(live_run)
        if request.method == "GET" and path.endswith("/reply-suggestions/latest"):
            return _response(live_run)
        if request.method == "POST" and "/candidates/" in path and path.endswith("/select"):
            return _response(
                {
                    "run_id": RUN_ID,
                    "candidate_id": CANDIDATE_ID,
                    "outbound_message_id": DRAFT_ID,
                    "draft_status": "draft",
                }
            )
        raise AssertionError(f"unexpected request: {request.method} {path}")

    summary = run_smoke(
        api_url="https://api-staging.example.com",
        web_origin="https://web-staging.example.com",
        email="owner@example.invalid",
        password="synthetic-password",
        expected_provider="openai",
        expected_model="deepseek-v4-flash",
        expected_tenant_id=TENANT_ID,
        expected_thread_id=THREAD_ID,
        expect_disabled=False,
        select_candidate=True,
        transport=httpx.MockTransport(handler),
    )

    assert summary["status"] == "passed"
    assert summary["provider_code"] == "openai"
    assert summary["input_tokens"] == 132
    assert summary["candidate_count"] == 1
    assert summary["draft_created"] is True
    assert summary["draft_id"] == DRAFT_ID


def test_kill_switch_smoke_accepts_only_blocked_provider_failure() -> None:
    disabled_run: dict[str, object] = {
        "id": RUN_ID,
        "conversation_thread_id": THREAD_ID,
        "status": "blocked",
        "provider_code": None,
        "model_code": None,
        "input_tokens": None,
        "output_tokens": None,
        "latency_milliseconds": None,
        "cost_status": "unknown",
        "estimated_cost_microunits": None,
        "failure_code": "provider_failure",
        "candidates": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        common = _common_handler(request)
        if common is not None:
            return common
        if request.method == "POST" and request.url.path.endswith("/reply-suggestions"):
            return _response(disabled_run)
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    summary = run_smoke(
        api_url="https://api-staging.example.com",
        web_origin="https://web-staging.example.com",
        email="owner@example.invalid",
        password="synthetic-password",
        expected_provider="openai",
        expected_model="deepseek-v4-flash",
        expected_tenant_id=TENANT_ID,
        expected_thread_id=THREAD_ID,
        expect_disabled=True,
        select_candidate=False,
        transport=httpx.MockTransport(handler),
    )

    assert summary["mode"] == "disabled"
    assert summary["candidate_count"] == 0
    assert summary["draft_created"] is False


def test_live_smoke_rejects_missing_provider_telemetry() -> None:
    invalid_run = _live_run()
    invalid_run["latency_milliseconds"] = None

    def handler(request: httpx.Request) -> httpx.Response:
        common = _common_handler(request)
        if common is not None:
            return common
        if request.method == "POST" and request.url.path.endswith("/reply-suggestions"):
            return _response(invalid_run)
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    with pytest.raises(SmokeFailure, match="latency_milliseconds"):
        run_smoke(
            api_url="https://api-staging.example.com",
            web_origin="https://web-staging.example.com",
            email="owner@example.invalid",
            password="synthetic-password",
            expected_provider="openai",
            expected_model="deepseek-v4-flash",
            expected_tenant_id=TENANT_ID,
            expected_thread_id=THREAD_ID,
            expect_disabled=False,
            select_candidate=False,
            transport=httpx.MockTransport(handler),
        )


def test_ids_used_by_test_are_valid_uuids() -> None:
    for value in (TENANT_ID, THREAD_ID, RUN_ID, CANDIDATE_ID, DRAFT_ID):
        UUID(value)
