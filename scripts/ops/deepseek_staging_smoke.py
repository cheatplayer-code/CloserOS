#!/usr/bin/env python3
"""End-to-end staging smoke for live DeepSeek Reply Copilot wiring."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "backend" / "src"))

from closeros_api.auth_security import CSRF_HEADER_NAME  # noqa: E402

_SENSITIVE_MARKERS = (
    "api_key",
    "authorization",
    "bearer",
    "cookie",
    "csrf_token",
    "password",
    "prompt_text",
    "output_text",
)


class SmokeFailure(Exception):
    """Raised when a staging acceptance assertion fails."""


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SmokeFailure(f"{name} is not set")
    return value


def _safe_payload(payload: object) -> None:
    """Reject sensitive response field names without inspecting customer text values."""

    if isinstance(payload, dict):
        for raw_key, value in payload.items():
            normalized_key = str(raw_key).casefold()
            for marker in _SENSITIVE_MARKERS:
                if marker in normalized_key:
                    raise SmokeFailure(
                        f"unsafe field appeared in response JSON: {marker}"
                    )
            _safe_payload(value)
        return
    if isinstance(payload, list):
        for item in payload:
            _safe_payload(item)


def _require_status(response: httpx.Response, expected: int, operation: str) -> None:
    if response.status_code != expected:
        request_id = response.headers.get("x-request-id", "unavailable")
        raise SmokeFailure(
            f"{operation} returned HTTP {response.status_code}; request_id={request_id}"
        )


def _select_tenant(
    tenants: list[dict[str, Any]],
    expected_tenant_id: str | None,
) -> dict[str, Any]:
    if expected_tenant_id:
        for tenant in tenants:
            if str(tenant.get("id")) == expected_tenant_id:
                return tenant
        raise SmokeFailure("expected tenant was not returned by the API")
    if not tenants:
        raise SmokeFailure("smoke user has no tenant")
    return tenants[0]


def _select_thread(
    conversations: list[dict[str, Any]],
    expected_thread_id: str | None,
) -> str:
    if expected_thread_id:
        for item in conversations:
            if str(item.get("id")) == expected_thread_id:
                return expected_thread_id
        raise SmokeFailure("expected conversation thread was not returned by the API")
    if not conversations:
        raise SmokeFailure("staging tenant has no synthetic conversation")
    thread_id = conversations[0].get("id")
    if not isinstance(thread_id, str):
        raise SmokeFailure("conversation thread id is invalid")
    return thread_id


def _validate_disabled_run(payload: dict[str, Any]) -> None:
    if payload.get("status") != "blocked":
        raise SmokeFailure("kill switch did not produce a blocked reply run")
    if payload.get("failure_code") != "provider_failure":
        raise SmokeFailure("kill switch did not report the expected provider failure code")
    if payload.get("provider_code") is not None or payload.get("model_code") is not None:
        raise SmokeFailure("disabled external AI exposed a configured provider or model")
    if payload.get("candidates"):
        raise SmokeFailure("disabled external AI produced reply candidates")


def _positive_integer(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SmokeFailure(f"{field} was not a positive integer")
    return value


def _validate_live_run(
    payload: dict[str, Any],
    *,
    expected_provider: str,
    expected_model: str,
) -> tuple[int, int, int, list[dict[str, Any]]]:
    if payload.get("status") != "completed":
        raise SmokeFailure(
            f"reply run did not complete; failure_code={payload.get('failure_code') or 'none'}"
        )
    if payload.get("failure_code") is not None:
        raise SmokeFailure("completed reply run contains a failure code")
    if payload.get("provider_code") != expected_provider:
        raise SmokeFailure("actual provider metadata does not match the expected provider")
    if payload.get("model_code") != expected_model:
        raise SmokeFailure("actual model metadata does not match the expected model")

    input_tokens = _positive_integer(payload, "input_tokens")
    output_tokens = _positive_integer(payload, "output_tokens")
    latency_milliseconds = _positive_integer(payload, "latency_milliseconds")

    cost_status = payload.get("cost_status")
    estimated_cost = payload.get("estimated_cost_microunits")
    if cost_status not in {"known", "unknown"}:
        raise SmokeFailure("external reply run has an invalid cost status")
    if cost_status == "known" and (
        not isinstance(estimated_cost, int)
        or isinstance(estimated_cost, bool)
        or estimated_cost <= 0
    ):
        raise SmokeFailure("known external cost is not a positive integer")
    if cost_status == "unknown" and estimated_cost is not None:
        raise SmokeFailure("unknown external cost must not include an estimate")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise SmokeFailure("live provider produced no validated candidates")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise SmokeFailure("candidate payload is invalid")
        evidence = candidate.get("evidence_message_ids")
        if not isinstance(evidence, list) or not evidence:
            raise SmokeFailure("candidate is missing evidence message ids")

    return input_tokens, output_tokens, latency_milliseconds, candidates


def run_smoke(
    *,
    api_url: str,
    web_origin: str,
    email: str,
    password: str,
    expected_provider: str,
    expected_model: str,
    expected_tenant_id: str | None,
    expected_thread_id: str | None,
    expect_disabled: bool,
    select_candidate: bool,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, object]:
    base_url = api_url.rstrip("/")
    origin = web_origin.rstrip("/")
    timeout = httpx.Timeout(60.0, connect=15.0)
    with httpx.Client(
        base_url=base_url,
        timeout=timeout,
        follow_redirects=False,
        transport=transport,
    ) as client:
        health = client.get("/health")
        _require_status(health, 200, "health")
        ready = client.get("/ready")
        _require_status(ready, 200, "ready")
        ready_payload = ready.json()
        if ready_payload.get("status") != "ready":
            raise SmokeFailure("ready endpoint did not report ready")

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        _require_status(login, 200, "login")
        login_payload = login.json()
        csrf_token = login_payload.get("csrf_token")
        if not isinstance(csrf_token, str) or not csrf_token:
            raise SmokeFailure("login did not return a CSRF token")

        tenants_response = client.get("/api/v1/tenants")
        _require_status(tenants_response, 200, "tenant listing")
        tenants_payload = tenants_response.json()
        if not isinstance(tenants_payload, list):
            raise SmokeFailure("tenant listing payload is invalid")
        tenant = _select_tenant(tenants_payload, expected_tenant_id)
        tenant_id = str(tenant.get("id"))
        UUID(tenant_id)

        conversations_response = client.get(f"/api/v1/tenants/{tenant_id}/conversations")
        _require_status(conversations_response, 200, "conversation listing")
        conversations_payload = conversations_response.json()
        conversations = conversations_payload.get("conversations")
        if not isinstance(conversations, list):
            raise SmokeFailure("conversation listing payload is invalid")
        thread_id = _select_thread(conversations, expected_thread_id)
        UUID(thread_id)

        idempotency_key = f"s2-deepseek-smoke-{uuid4()}"
        mutation_headers = {
            CSRF_HEADER_NAME: csrf_token,
            "Origin": origin,
            "Idempotency-Key": idempotency_key,
        }
        generation = client.post(
            f"/api/v1/tenants/{tenant_id}/conversations/{thread_id}/reply-suggestions",
            headers=mutation_headers,
            json={"idempotency_key": idempotency_key},
        )
        _require_status(generation, 200, "reply suggestion generation")
        run_payload = generation.json()
        if not isinstance(run_payload, dict):
            raise SmokeFailure("reply run payload is invalid")
        _safe_payload(run_payload)

        selected_draft_id: str | None = None
        if expect_disabled:
            _validate_disabled_run(run_payload)
            input_tokens = output_tokens = latency_milliseconds = 0
            candidates: list[dict[str, Any]] = []
        else:
            input_tokens, output_tokens, latency_milliseconds, candidates = _validate_live_run(
                run_payload,
                expected_provider=expected_provider,
                expected_model=expected_model,
            )
            latest = client.get(
                f"/api/v1/tenants/{tenant_id}/conversations/{thread_id}/reply-suggestions/latest"
            )
            _require_status(latest, 200, "latest reply suggestion")
            latest_payload = latest.json()
            if latest_payload.get("id") != run_payload.get("id"):
                raise SmokeFailure("latest reply suggestion does not match generated run")

            if select_candidate:
                candidate_id = candidates[0].get("id")
                if not isinstance(candidate_id, str):
                    raise SmokeFailure("candidate id is invalid")
                selection = client.post(
                    f"/api/v1/tenants/{tenant_id}/reply-suggestions/{run_payload['id']}/candidates/{candidate_id}/select",
                    headers={CSRF_HEADER_NAME: csrf_token, "Origin": origin},
                    json={},
                )
                _require_status(selection, 200, "candidate selection")
                selection_payload = selection.json()
                if selection_payload.get("draft_status") != "draft":
                    raise SmokeFailure("candidate selection did not create a draft")
                selected_draft_id = str(selection_payload.get("outbound_message_id"))
                UUID(selected_draft_id)

        logout = client.post(
            "/api/v1/auth/logout",
            headers={CSRF_HEADER_NAME: csrf_token, "Origin": origin},
        )
        _require_status(logout, 204, "logout")

    return {
        "status": "passed",
        "mode": "disabled" if expect_disabled else "live",
        "tenant_id": tenant_id,
        "thread_id": thread_id,
        "run_id": str(run_payload.get("id")),
        "provider_code": run_payload.get("provider_code"),
        "model_code": run_payload.get("model_code"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_milliseconds": latency_milliseconds,
        "candidate_count": len(candidates),
        "draft_created": selected_draft_id is not None,
        "draft_id": selected_draft_id,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the S2 live DeepSeek staging acceptance smoke"
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("STAGING_API_URL", "").strip(),
        help="API base URL (defaults to STAGING_API_URL)",
    )
    parser.add_argument(
        "--web-origin",
        default=os.environ.get("STAGING_WEB_URL", "").strip(),
        help="allowed browser origin used for CSRF checks (defaults to STAGING_WEB_URL)",
    )
    parser.add_argument(
        "--expected-provider",
        default=os.environ.get("SMOKE_EXPECTED_AI_PROVIDER", "openai").strip(),
    )
    parser.add_argument(
        "--expected-model",
        default=os.environ.get("SMOKE_EXPECTED_AI_MODEL", "").strip()
        or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
    )
    parser.add_argument(
        "--expected-tenant-id",
        default=os.environ.get("SMOKE_EXPECTED_TENANT_ID", "").strip(),
    )
    parser.add_argument(
        "--thread-id",
        default=os.environ.get("SMOKE_CONVERSATION_THREAD_ID", "").strip(),
    )
    parser.add_argument(
        "--expect-disabled",
        action="store_true",
        help="verify the external-AI kill switch instead of a live provider call",
    )
    parser.add_argument(
        "--select-candidate",
        action="store_true",
        help="select the first validated candidate and assert encrypted draft creation",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.api_url:
        print("error: STAGING_API_URL is not set", file=sys.stderr)
        return 2
    if not args.web_origin:
        print("error: STAGING_WEB_URL is not set", file=sys.stderr)
        return 2
    try:
        summary = run_smoke(
            api_url=args.api_url,
            web_origin=args.web_origin,
            email=_required_env("SMOKE_USER_EMAIL"),
            password=_required_env("SMOKE_USER_PASSWORD"),
            expected_provider=args.expected_provider,
            expected_model=args.expected_model,
            expected_tenant_id=args.expected_tenant_id or None,
            expected_thread_id=args.thread_id or None,
            expect_disabled=args.expect_disabled,
            select_candidate=args.select_candidate,
        )
    except (SmokeFailure, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"error: HTTP request failed: {error.__class__.__name__}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
