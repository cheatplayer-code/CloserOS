#!/usr/bin/env python3
"""HTTP smoke checks for synthetic staging environments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "backend" / "src"))

from closeros.application.metrics_windows import (  # noqa: E402
    local_date_from_timestamp,
    rolling_30_day_window_for_local_date,
)
from closeros_api.auth_security import CSRF_HEADER_NAME  # noqa: E402

_SENSITIVE_SUBSTRINGS = (
    "password",
    "csrf",
    "session",
    "cookie",
    "bearer",
    "authorization",
)


class SmokeFailure(Exception):
    """Raised when a smoke assertion fails."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run synthetic staging HTTP smoke checks")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("STAGING_API_URL", "").strip(),
        help="API base URL (defaults to STAGING_API_URL)",
    )
    parser.add_argument(
        "--expected-tenant-id",
        default=os.environ.get("SMOKE_EXPECTED_TENANT_ID", "").strip(),
        help="Optional expected tenant UUID",
    )
    return parser.parse_args()


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SmokeFailure(f"{name} is not set")
    return value


def _assert_safe_json(payload: object) -> None:
    encoded = json.dumps(payload).lower()
    for marker in _SENSITIVE_SUBSTRINGS:
        if marker in encoded and marker != "session":
            raise SmokeFailure(f"unsafe marker appeared in response JSON: {marker}")


def _select_tenant(tenants: list[dict[str, Any]], expected: str | None) -> dict[str, Any]:
    if expected:
        for tenant in tenants:
            if str(tenant.get("id")) == expected:
                return tenant
        raise SmokeFailure("expected tenant was not returned by the API")
    if not tenants:
        raise SmokeFailure("no tenants available for smoke user")
    return tenants[0]


def _dashboard_window(*, time_zone: str) -> tuple[str, str]:
    now = datetime.now(tz=UTC)
    window = rolling_30_day_window_for_local_date(
        local_date=local_date_from_timestamp(occurred_at=now, time_zone=time_zone),
        time_zone=time_zone,
    )
    return window.start.isoformat(), window.end.isoformat()


def run_smoke(
    *, api_url: str, email: str, password: str, expected_tenant_id: str | None
) -> dict[str, object]:
    base = api_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30.0, follow_redirects=True) as client:
        health = client.get("/health")
        if health.status_code >= 500:
            raise SmokeFailure("health endpoint returned 5xx")
        ready = client.get("/ready")
        if ready.status_code >= 500:
            raise SmokeFailure("ready endpoint returned 5xx")

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if login.status_code >= 500:
            raise SmokeFailure("login returned 5xx")
        if login.status_code != 200:
            raise SmokeFailure("login failed")
        login_body = login.json()
        csrf = login_body.get("csrf_token")
        if not isinstance(csrf, str) or not csrf:
            raise SmokeFailure("login did not return csrf token")
        _assert_safe_json(login_body)

        tenants_response = client.get("/api/v1/tenants")
        if tenants_response.status_code >= 500:
            raise SmokeFailure("tenant listing returned 5xx")
        tenants_payload = tenants_response.json()
        if not isinstance(tenants_payload, list):
            raise SmokeFailure("tenant listing payload is invalid")
        tenant = _select_tenant(tenants_payload, expected_tenant_id)
        tenant_id = str(tenant["id"])
        time_zone = str(tenant.get("time_zone") or "UTC")

        window_start, window_end = _dashboard_window(time_zone=time_zone)
        dashboard = client.get(
            f"/api/v1/tenants/{tenant_id}/dashboard",
            params={"window_start": window_start, "window_end": window_end},
        )
        if dashboard.status_code >= 500:
            raise SmokeFailure("dashboard returned 5xx")
        dashboard_body = dashboard.json()
        if dashboard_body.get("total_conversations", 0) < 1:
            raise SmokeFailure("dashboard is empty")

        conversations = client.get(f"/api/v1/tenants/{tenant_id}/conversations")
        if conversations.status_code >= 500:
            raise SmokeFailure("conversations returned 5xx")
        conversation_items = conversations.json().get("conversations", [])
        if not conversation_items:
            raise SmokeFailure("no conversations returned")
        thread_id = conversation_items[0]["id"]
        conversation_detail = client.get(
            f"/api/v1/tenants/{tenant_id}/conversations/{thread_id}",
        )
        if conversation_detail.status_code >= 500:
            raise SmokeFailure("conversation detail returned 5xx")
        detail_body = conversation_detail.json()
        analyses = detail_body.get("analyses", [])
        has_evidence = any(
            finding.get("evidence")
            for analysis in analyses
            for finding in analysis.get("findings", [])
        )
        if not has_evidence:
            raise SmokeFailure("evidence-backed finding missing")

        managers = client.get(f"/api/v1/tenants/{tenant_id}/managers")
        if managers.status_code >= 500:
            raise SmokeFailure("managers returned 5xx")
        manager_items = managers.json().get("managers", [])
        if not manager_items:
            raise SmokeFailure("no managers returned")
        membership_id = manager_items[0]["membership_id"]
        scorecard = client.get(
            f"/api/v1/tenants/{tenant_id}/managers/{membership_id}/scorecard",
            params={"window_start": window_start, "window_end": window_end},
        )
        if scorecard.status_code >= 500:
            raise SmokeFailure("manager scorecard returned 5xx")

        tasks = client.get(f"/api/v1/tenants/{tenant_id}/tasks")
        if tasks.status_code >= 500:
            raise SmokeFailure("tasks returned 5xx")
        task_items = tasks.json().get("tasks", [])
        if not task_items:
            raise SmokeFailure("no tasks returned")

        metrics = client.get(
            f"/api/v1/tenants/{tenant_id}/metrics",
            params={
                "scope": "tenant",
                "window_start": window_start,
                "window_end": window_end,
            },
        )
        if metrics.status_code >= 500:
            raise SmokeFailure("metrics returned 5xx")

        anonymous = httpx.Client(base_url=base, timeout=30.0)
        try:
            protected = anonymous.get(
                f"/api/v1/tenants/{tenant_id}/dashboard",
                params={"window_start": window_start, "window_end": window_end},
            )
            if protected.status_code not in {401, 403}:
                raise SmokeFailure("protected route did not reject anonymous access")
        finally:
            anonymous.close()

        logout = client.post(
            "/api/v1/auth/logout",
            headers={CSRF_HEADER_NAME: csrf, "Origin": base},
        )
        if logout.status_code >= 500:
            raise SmokeFailure("logout returned 5xx")

        return {
            "status": "passed",
            "tenant_id": tenant_id,
            "dashboard": "ok",
            "conversations": len(conversation_items),
            "tasks": len(task_items),
        }


def main() -> int:
    args = _parse_args()
    if not args.api_url:
        print("error: STAGING_API_URL is not set and --api-url was not provided", file=sys.stderr)
        return 2
    try:
        email = _require_env("SMOKE_USER_EMAIL")
        password = _require_env("SMOKE_USER_PASSWORD")
        summary = run_smoke(
            api_url=args.api_url,
            email=email,
            password=password,
            expected_tenant_id=args.expected_tenant_id or None,
        )
    except SmokeFailure as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"error: http request failed: {error.__class__.__name__}", file=sys.stderr)
        return 1

    if args.expected_tenant_id:
        try:
            if summary["tenant_id"] != str(UUID(args.expected_tenant_id)):
                print("error: selected tenant does not match expectation", file=sys.stderr)
                return 3
        except ValueError:
            print("error: expected tenant id must be a UUID", file=sys.stderr)
            return 4

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
