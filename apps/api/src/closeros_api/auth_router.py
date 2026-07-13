"""Authentication HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any, cast

from closeros.application.audit_recording import AuditContext
from closeros.application.authentication_workflows import (
    AuthenticationFailedError,
    AuthenticationWorkflowUnavailableError,
    RegistrationUnavailableError,
)
from closeros.domain.authentication import AuthenticationSessionStage, MfaMethod
from closeros.security.authentication_tokens import RawAuthenticationToken
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from closeros_api.auth_schemas import (
    AcceptedResponse,
    EmailOnlyRequest,
    LoginRequest,
    LoginResponse,
    MfaCompleteRequest,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
    SessionResponse,
    VerificationConfirmRequest,
)
from closeros_api.auth_security import (
    CSRF_HEADER_NAME,
    apply_security_headers,
    clear_session_cookie,
    client_ip,
    csrf_token_is_valid,
    fingerprint_value,
    generate_csrf_token,
    origin_is_allowed,
    read_session_cookie,
    set_session_cookie,
)
from closeros_api.composition import AuthRuntime
from closeros_api.request_correlation import get_request_correlation_id

router = APIRouter(tags=["authentication"])

AUTHENTICATION_FAILED = "authentication failed"
ACCESS_DENIED = "access denied"
REQUEST_ACCEPTED = "request accepted"
RATE_LIMITED = "too many requests"
REQUEST_UNAVAILABLE = "request unavailable"


def _audit_context(request: Request) -> AuditContext:
    route = request.scope.get("route")
    route_template = getattr(route, "path", None)
    return AuditContext(
        correlation_id=get_request_correlation_id(request),
        http_method=request.method,
        route_template=route_template if isinstance(route_template, str) else None,
    )


def _runtime(request: Request) -> AuthRuntime:
    runtime = getattr(request.app.state, "auth", None)
    if runtime is None:
        raise RuntimeError("authentication runtime is not configured")
    return cast(AuthRuntime, runtime)


RuntimeDep = Annotated[AuthRuntime, Depends(_runtime)]


def _json_response(content: dict[str, Any], *, status_code: int) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=content)
    apply_security_headers(response)
    return response


async def _enforce_rate_limit(
    runtime: AuthRuntime,
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
    account_fingerprint: str | None = None,
) -> None:
    ip = client_ip(
        request,
        trust_forwarded_client_ip=runtime.settings.trust_forwarded_client_ip,
    )
    ip_key = fingerprint_value(
        secret=runtime.settings.auth_rate_limit_secret,
        value=ip,
    )
    key = ip_key if account_fingerprint is None else f"{ip_key}:{account_fingerprint}"
    decision = await runtime.rate_limiter.check(
        scope=scope,
        key=key,
        limit=limit,
        window_seconds=window_seconds,
    )
    if not decision.allowed:
        headers = {"Retry-After": str(decision.retry_after_seconds or window_seconds)}
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMITED,
            headers=headers,
        )


def _account_fingerprint(runtime: AuthRuntime, email: str) -> str:
    return fingerprint_value(
        secret=runtime.settings.auth_rate_limit_secret,
        value=email.strip().lower(),
    )


def _session_fingerprint(runtime: AuthRuntime, session_token: RawAuthenticationToken) -> str:
    return fingerprint_value(
        secret=runtime.settings.auth_rate_limit_secret,
        value=session_token.value,
    )


def _require_origin(request: Request, runtime: AuthRuntime) -> None:
    origin = request.headers.get("origin")
    if not origin_is_allowed(
        origin=origin,
        allowed_origins=runtime.settings.auth_allowed_origins,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _require_csrf(
    request: Request,
    runtime: AuthRuntime,
    session_token: RawAuthenticationToken,
) -> None:
    provided = request.headers.get(CSRF_HEADER_NAME)
    if provided is None or not csrf_token_is_valid(
        session_token=session_token,
        secret=runtime.settings.auth_csrf_secret,
        provided_token=provided,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED)


def _login_response(
    *,
    runtime: AuthRuntime,
    issued: Any,
    raw_token: RawAuthenticationToken,
) -> LoginResponse:
    csrf_token = generate_csrf_token(
        session_token=raw_token,
        secret=runtime.settings.auth_csrf_secret,
    )
    if issued.session.stage is AuthenticationSessionStage.PENDING_MFA:
        return LoginResponse(
            state="mfa_required",
            csrf_token=csrf_token,
            expires_at=issued.session.expires_at,
        )
    return LoginResponse(
        state="authenticated",
        csrf_token=csrf_token,
        expires_at=issued.session.expires_at,
        user_id=issued.session.user_id,
        session_id=issued.session.id,
        assurance_level=issued.session.assurance_level.value,
    )


async def _dispatch_safely(awaitable: Any) -> None:
    try:
        await awaitable
    except Exception:
        return None


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> AcceptedResponse:
    await _enforce_rate_limit(
        runtime,
        request,
        scope="register",
        limit=5,
        window_seconds=3600,
    )
    try:
        result = await runtime.workflows.register_user(
            user_id=runtime.uuid_factory(),
            credential_id=runtime.uuid_factory(),
            verification_token_id=runtime.uuid_factory(),
            email=body.email,
            plaintext_password=body.password.get_secret_value(),
            registered_at=runtime.clock.now(),
            audit_context=_audit_context(request),
        )
        if result.delivery is not None:
            await _dispatch_safely(
                runtime.notification_dispatcher.dispatch_email_verification(result.delivery)
            )
    except RegistrationUnavailableError:
        pass

    apply_security_headers(response)
    return AcceptedResponse(message=REQUEST_ACCEPTED)


@router.post(
    "/email-verification/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
)
async def request_email_verification(
    body: EmailOnlyRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> AcceptedResponse:
    await _enforce_rate_limit(
        runtime,
        request,
        scope="email_verification_request",
        limit=5,
        window_seconds=3600,
        account_fingerprint=_account_fingerprint(runtime, body.email),
    )
    accepted = await runtime.workflows.request_email_verification(
        email=body.email,
        verification_token_id=runtime.uuid_factory(),
        requested_at=runtime.clock.now(),
        audit_context=_audit_context(request),
    )
    if accepted.delivery is not None:
        await _dispatch_safely(
            runtime.notification_dispatcher.dispatch_email_verification(accepted.delivery)
        )
    apply_security_headers(response)
    return AcceptedResponse(message=REQUEST_ACCEPTED)


@router.post("/email-verification/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email_verification(
    body: VerificationConfirmRequest,
    request: Request,
    runtime: RuntimeDep,
) -> Response:
    await _enforce_rate_limit(
        runtime,
        request,
        scope="email_verification_confirm",
        limit=10,
        window_seconds=3600,
    )
    try:
        raw_token = RawAuthenticationToken(body.verification_token)
        await runtime.workflows.confirm_email_verification(
            raw_token=raw_token,
            confirmed_at=runtime.clock.now(),
            audit_context=_audit_context(request),
        )
    except (AuthenticationWorkflowUnavailableError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=REQUEST_UNAVAILABLE,
        ) from None

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    apply_security_headers(response)
    return response


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> LoginResponse:
    await _enforce_rate_limit(
        runtime,
        request,
        scope="login",
        limit=10,
        window_seconds=900,
        account_fingerprint=_account_fingerprint(runtime, body.email),
    )
    try:
        issued = await runtime.workflows.login_with_password(
            email=body.email,
            plaintext_password=body.password.get_secret_value(),
            session_id=runtime.uuid_factory(),
            authenticated_at=runtime.clock.now(),
            audit_context=_audit_context(request),
            mfa_requirement_policy=runtime.mfa_requirement_policy,
        )
    except AuthenticationFailedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None

    login_payload = _login_response(
        runtime=runtime,
        issued=issued,
        raw_token=issued.raw_token,
    )
    set_session_cookie(
        response,
        session_token=issued.raw_token,
        expires_at=issued.session.expires_at,
        cookie_config=runtime.cookie_config,
        now=runtime.clock.now(),
    )
    apply_security_headers(response)
    return login_payload


@router.post("/mfa/complete", response_model=LoginResponse)
async def complete_mfa(
    body: MfaCompleteRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> LoginResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    _require_origin(request, runtime)
    _require_csrf(request, runtime, session_token)
    await _enforce_rate_limit(
        runtime,
        request,
        scope="mfa_complete",
        limit=10,
        window_seconds=900,
        account_fingerprint=_session_fingerprint(runtime, session_token),
    )

    try:
        issued = await runtime.workflows.complete_mfa_login(
            pending_session_raw_token=session_token,
            new_session_id=runtime.uuid_factory(),
            method=MfaMethod(body.method),
            mfa_response=body.response,
            completed_at=runtime.clock.now(),
            audit_context=_audit_context(request),
            mfa_verifier=runtime.mfa_verifier,
        )
    except AuthenticationWorkflowUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None

    login_payload = _login_response(
        runtime=runtime,
        issued=issued,
        raw_token=issued.raw_token,
    )
    set_session_cookie(
        response,
        session_token=issued.raw_token,
        expires_at=issued.session.expires_at,
        cookie_config=runtime.cookie_config,
        now=runtime.clock.now(),
    )
    apply_security_headers(response)
    return login_payload


@router.get("/session", response_model=SessionResponse)
async def get_session(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> SessionResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    try:
        resolved = await runtime.workflows.resolve_session(
            raw_token=session_token,
            now=runtime.clock.now(),
        )
    except AuthenticationWorkflowUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None

    if resolved.session.stage is not AuthenticationSessionStage.AUTHENTICATED:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    payload = SessionResponse(
        user_id=resolved.user.id,
        session_id=resolved.session.id,
        assurance_level=resolved.session.assurance_level.value,
        expires_at=resolved.session.expires_at,
        csrf_token=generate_csrf_token(
            session_token=session_token,
            secret=runtime.settings.auth_csrf_secret,
        ),
    )
    apply_security_headers(response)
    return payload


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> Response:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is not None:
        _require_origin(request, runtime)
        _require_csrf(request, runtime, session_token)
        await runtime.workflows.logout(
            raw_token=session_token,
            revoked_at=runtime.clock.now(),
            audit_context=_audit_context(request),
        )

    clear_session_cookie(response, cookie_config=runtime.cookie_config)
    response.status_code = status.HTTP_204_NO_CONTENT
    apply_security_headers(response)
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> Response:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    _require_origin(request, runtime)
    _require_csrf(request, runtime, session_token)

    try:
        resolved = await runtime.workflows.resolve_session(
            raw_token=session_token,
            now=runtime.clock.now(),
            touch_session=False,
        )
    except AuthenticationWorkflowUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None

    await runtime.workflows.logout_all_sessions(
        user_id=resolved.user.id,
        revoked_at=runtime.clock.now(),
        audit_context=_audit_context(request),
    )
    clear_session_cookie(response, cookie_config=runtime.cookie_config)
    response.status_code = status.HTTP_204_NO_CONTENT
    apply_security_headers(response)
    return response


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
)
async def request_password_reset(
    body: EmailOnlyRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> AcceptedResponse:
    await _enforce_rate_limit(
        runtime,
        request,
        scope="password_reset_request",
        limit=5,
        window_seconds=3600,
        account_fingerprint=_account_fingerprint(runtime, body.email),
    )
    accepted = await runtime.workflows.request_password_reset(
        email=body.email,
        reset_token_id=runtime.uuid_factory(),
        requested_at=runtime.clock.now(),
        audit_context=_audit_context(request),
    )
    if accepted.delivery is not None:
        await _dispatch_safely(
            runtime.notification_dispatcher.dispatch_password_reset(accepted.delivery)
        )
    apply_security_headers(response)
    return AcceptedResponse(message=REQUEST_ACCEPTED)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> Response:
    await _enforce_rate_limit(
        runtime,
        request,
        scope="password_reset_confirm",
        limit=10,
        window_seconds=3600,
    )
    try:
        raw_token = RawAuthenticationToken(body.reset_token)
        await runtime.workflows.confirm_password_reset(
            raw_token=raw_token,
            new_plaintext_password=body.new_password.get_secret_value(),
            confirmed_at=runtime.clock.now(),
            audit_context=_audit_context(request),
        )
    except (AuthenticationWorkflowUnavailableError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=REQUEST_UNAVAILABLE,
        ) from None

    clear_session_cookie(response, cookie_config=runtime.cookie_config)
    response.status_code = status.HTTP_204_NO_CONTENT
    apply_security_headers(response)
    return response


@router.post("/password/change", response_model=LoginResponse)
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    response: Response,
    runtime: RuntimeDep,
) -> LoginResponse:
    session_token = read_session_cookie(request, cookie_config=runtime.cookie_config)
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTHENTICATION_FAILED)

    _require_origin(request, runtime)
    _require_csrf(request, runtime, session_token)
    await _enforce_rate_limit(
        runtime,
        request,
        scope="password_change",
        limit=5,
        window_seconds=3600,
        account_fingerprint=_session_fingerprint(runtime, session_token),
    )

    try:
        issued = await runtime.workflows.change_password(
            session_raw_token=session_token,
            current_password=body.current_password.get_secret_value(),
            new_password=body.new_password.get_secret_value(),
            new_session_id=runtime.uuid_factory(),
            changed_at=runtime.clock.now(),
            audit_context=_audit_context(request),
        )
    except AuthenticationFailedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None
    except AuthenticationWorkflowUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_FAILED,
        ) from None

    login_payload = _login_response(
        runtime=runtime,
        issued=issued,
        raw_token=issued.raw_token,
    )
    set_session_cookie(
        response,
        session_token=issued.raw_token,
        expires_at=issued.session.expires_at,
        cookie_config=runtime.cookie_config,
        now=runtime.clock.now(),
    )
    apply_security_headers(response)
    return login_payload
