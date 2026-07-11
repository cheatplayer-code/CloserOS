"""Tests for CLS-011.3g MFA-completion session rotation service."""

# mypy: disable-error-code=import-untyped

from base64 import urlsafe_b64encode
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.application import (
    AuthenticationSessionRotation,
    AuthenticationSessionTransitionError,
    complete_pending_mfa_and_rotate_session,
    issue_authenticated_session,
    issue_pending_mfa_session,
)
from closeros.domain import (
    AuthenticationAssuranceLevel,
    AuthenticationSession,
    AuthenticationSessionStage,
    AuthenticationSessionTimeoutPolicy,
    AuthenticationSessionUnavailableError,
)
from closeros.security import RawAuthenticationToken, hash_authentication_token

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")
NEW_SESSION_ID = UUID("00000000-0000-0000-0000-000000000004")

CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
COMPLETED_AT = CREATED_AT + timedelta(minutes=1)

CUSTOM_SESSION_POLICY = AuthenticationSessionTimeoutPolicy(
    authenticated_idle_timeout=timedelta(minutes=7),
    authenticated_absolute_timeout=timedelta(hours=3),
    pending_mfa_timeout=timedelta(minutes=10),
)


def _raw_token_from_bytes(raw: bytes) -> RawAuthenticationToken:
    return RawAuthenticationToken(urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"))


RAW_TOKEN_PENDING = _raw_token_from_bytes(bytes(range(32)))
RAW_TOKEN_NEW = _raw_token_from_bytes(bytes(reversed(range(32))))


class RecordingRawTokenFactory:
    def __init__(self, raw_token: RawAuthenticationToken) -> None:
        self._raw_token = raw_token
        self.calls = 0

    def __call__(self) -> RawAuthenticationToken:
        self.calls += 1
        return self._raw_token


def _pending_session(
    *,
    policy: AuthenticationSessionTimeoutPolicy | None = None,
) -> AuthenticationSession:
    issued = issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=CREATED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_PENDING),
        timeout_policy=policy if policy is not None else _canonical_policy(),
    )
    return issued.session


def _canonical_policy() -> AuthenticationSessionTimeoutPolicy:
    return AuthenticationSessionTimeoutPolicy(
        authenticated_idle_timeout=timedelta(minutes=30),
        authenticated_absolute_timeout=timedelta(hours=12),
        pending_mfa_timeout=timedelta(minutes=5),
    )


def _rotate(
    pending: AuthenticationSession,
    *,
    new_session_id: UUID = NEW_SESSION_ID,
    completed_at: datetime = COMPLETED_AT,
    policy: AuthenticationSessionTimeoutPolicy | None = None,
    factory: RecordingRawTokenFactory | None = None,
) -> AuthenticationSessionRotation:
    return complete_pending_mfa_and_rotate_session(
        pending_session=pending,
        new_session_id=new_session_id,
        completed_at=completed_at,
        raw_token_factory=factory
        if factory is not None
        else RecordingRawTokenFactory(RAW_TOKEN_NEW),
        timeout_policy=policy if policy is not None else _canonical_policy(),
    )


def test_valid_pending_session_is_completed_successfully() -> None:
    rotation = _rotate(_pending_session())

    assert isinstance(rotation, AuthenticationSessionRotation)


def test_original_pending_session_is_not_mutated() -> None:
    pending = _pending_session()
    before = (
        pending.stage,
        pending.assurance_level,
        pending.mfa_completed,
        pending.revoked_at,
        pending.token_hash.digest,
    )

    _rotate(pending)

    assert (
        pending.stage,
        pending.assurance_level,
        pending.mfa_completed,
        pending.revoked_at,
        pending.token_hash.digest,
    ) == before


def test_returned_revoked_session_is_a_different_object() -> None:
    pending = _pending_session()

    rotation = _rotate(pending)

    assert rotation.revoked_session is not pending


def test_revoked_session_keeps_original_id() -> None:
    pending = _pending_session()

    rotation = _rotate(pending)

    assert rotation.revoked_session.id == pending.id


def test_revoked_session_keeps_original_user_id() -> None:
    pending = _pending_session()

    rotation = _rotate(pending)

    assert rotation.revoked_session.user_id == pending.user_id


def test_revoked_session_keeps_original_token_hash() -> None:
    pending = _pending_session()

    rotation = _rotate(pending)

    assert rotation.revoked_session.token_hash.digest == pending.token_hash.digest


def test_revoked_session_revoked_at_equals_completed_at() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.revoked_session.revoked_at == COMPLETED_AT


def test_new_session_uses_new_session_id() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.id == NEW_SESSION_ID


def test_new_session_uses_same_user_id() -> None:
    pending = _pending_session()

    rotation = _rotate(pending)

    assert rotation.issued.session.user_id == pending.user_id


def test_new_session_stage_is_authenticated() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.stage is AuthenticationSessionStage.AUTHENTICATED


def test_new_session_assurance_is_multi_factor() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.assurance_level is AuthenticationAssuranceLevel.MULTI_FACTOR


def test_new_session_mfa_completed_is_true() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.mfa_completed is True


def test_new_session_created_at_equals_completed_at() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.created_at == COMPLETED_AT


def test_new_session_last_seen_at_equals_completed_at() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.last_seen_at == COMPLETED_AT


def test_new_session_revoked_at_is_none() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.revoked_at is None


def test_new_session_canonical_expiry_is_completed_at_plus_12_hours() -> None:
    rotation = _rotate(_pending_session())

    assert rotation.issued.session.expires_at == COMPLETED_AT + timedelta(hours=12)


def test_custom_timeout_policy_controls_new_authenticated_expiry() -> None:
    pending = _pending_session(policy=CUSTOM_SESSION_POLICY)

    rotation = _rotate(pending, policy=CUSTOM_SESSION_POLICY)

    assert rotation.issued.session.expires_at == COMPLETED_AT + timedelta(hours=3)


def test_returned_raw_token_hashes_to_new_session_token_hash() -> None:
    rotation = _rotate(_pending_session())

    assert (
        hash_authentication_token(rotation.issued.raw_token).digest
        == rotation.issued.session.token_hash.digest
    )


def test_new_token_hash_differs_from_old_pending_token_hash() -> None:
    pending = _pending_session()

    rotation = _rotate(pending)

    assert rotation.issued.session.token_hash.digest != pending.token_hash.digest


def test_raw_token_factory_is_called_exactly_once() -> None:
    factory = RecordingRawTokenFactory(RAW_TOKEN_NEW)

    _rotate(_pending_session(), factory=factory)

    assert factory.calls == 1


def test_authenticated_input_session_is_denied() -> None:
    authenticated = issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        issued_at=CREATED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_PENDING),
    ).session

    with pytest.raises(
        AuthenticationSessionTransitionError,
        match="authentication session transition unavailable",
    ):
        _rotate(authenticated)


def test_same_old_and_new_session_id_is_denied() -> None:
    pending = _pending_session()

    with pytest.raises(
        AuthenticationSessionTransitionError,
        match="authentication session transition unavailable",
    ):
        _rotate(pending, new_session_id=SESSION_ID)


def test_transition_denial_message_is_exact_and_safe() -> None:
    pending = _pending_session()

    with pytest.raises(AuthenticationSessionTransitionError) as exc_info:
        _rotate(pending, new_session_id=SESSION_ID)

    message = str(exc_info.value)
    assert message == "authentication session transition unavailable"
    assert str(pending.id) not in message
    assert str(pending.user_id) not in message
    assert pending.stage.value not in message
    assert pending.assurance_level.value not in message
    assert "False" not in message
    assert str(CREATED_AT) not in message
    assert RAW_TOKEN_PENDING.value not in message


def test_expired_pending_session_propagates_unavailable_error() -> None:
    pending = _pending_session()

    with pytest.raises(AuthenticationSessionUnavailableError):
        _rotate(pending, completed_at=CREATED_AT + timedelta(minutes=6))


def test_revoked_pending_session_propagates_unavailable_error() -> None:
    pending = replace(
        _pending_session(),
        revoked_at=CREATED_AT + timedelta(seconds=30),
    )

    with pytest.raises(AuthenticationSessionUnavailableError):
        _rotate(pending)


def test_pending_session_before_created_at_propagates_unavailable_error() -> None:
    pending = _pending_session()

    with pytest.raises(AuthenticationSessionUnavailableError):
        _rotate(pending, completed_at=CREATED_AT - timedelta(minutes=1))


def test_pending_session_at_expiry_boundary_is_unavailable() -> None:
    pending = _pending_session()

    with pytest.raises(AuthenticationSessionUnavailableError):
        _rotate(pending, completed_at=pending.expires_at)


def test_wrong_pending_session_type_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="pending_session must be an AuthenticationSession",
    ):
        complete_pending_mfa_and_rotate_session(
            pending_session=cast(Any, object()),
            new_session_id=NEW_SESSION_ID,
            completed_at=COMPLETED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_NEW),
        )


def test_wrong_new_session_id_type_raises_type_error() -> None:
    pending = _pending_session()

    with pytest.raises(TypeError, match="new_session_id must be a UUID"):
        complete_pending_mfa_and_rotate_session(
            pending_session=pending,
            new_session_id=cast(Any, "not-a-uuid"),
            completed_at=COMPLETED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_NEW),
        )


def test_wrong_completed_at_type_raises_type_error() -> None:
    pending = _pending_session()

    with pytest.raises(TypeError, match="completed_at must be a datetime"):
        complete_pending_mfa_and_rotate_session(
            pending_session=pending,
            new_session_id=NEW_SESSION_ID,
            completed_at=cast(Any, "2026-07-11T12:01:00Z"),
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_NEW),
        )


def test_naive_completed_at_raises_value_error() -> None:
    pending = _pending_session()

    with pytest.raises(ValueError, match="completed_at must be timezone-aware"):
        complete_pending_mfa_and_rotate_session(
            pending_session=pending,
            new_session_id=NEW_SESSION_ID,
            completed_at=datetime(2026, 7, 11, 12, 1, 0),
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_NEW),
        )


def test_wrong_timeout_policy_type_raises_type_error() -> None:
    pending = _pending_session()

    with pytest.raises(
        TypeError,
        match="timeout_policy must be an AuthenticationSessionTimeoutPolicy",
    ):
        complete_pending_mfa_and_rotate_session(
            pending_session=pending,
            new_session_id=NEW_SESSION_ID,
            completed_at=COMPLETED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_NEW),
            timeout_policy=cast(Any, object()),
        )


def test_non_callable_factory_raises_type_error() -> None:
    pending = _pending_session()

    with pytest.raises(TypeError, match="raw_token_factory must be callable"):
        complete_pending_mfa_and_rotate_session(
            pending_session=pending,
            new_session_id=NEW_SESSION_ID,
            completed_at=COMPLETED_AT,
            raw_token_factory=cast(Any, object()),
        )


def test_factory_returning_wrong_type_raises_type_error() -> None:
    pending = _pending_session()

    with pytest.raises(
        TypeError,
        match="raw_token_factory must return a RawAuthenticationToken",
    ):
        complete_pending_mfa_and_rotate_session(
            pending_session=pending,
            new_session_id=NEW_SESSION_ID,
            completed_at=COMPLETED_AT,
            raw_token_factory=cast(Any, lambda: "not-a-token"),
        )


def test_failure_before_token_generation_does_not_call_factory() -> None:
    authenticated = issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        issued_at=CREATED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_PENDING),
    ).session
    factory = RecordingRawTokenFactory(RAW_TOKEN_NEW)

    with pytest.raises(AuthenticationSessionTransitionError):
        _rotate(authenticated, factory=factory)

    assert factory.calls == 0


def test_completion_does_not_mutate_custom_timeout_policy() -> None:
    before = (
        CUSTOM_SESSION_POLICY.authenticated_idle_timeout,
        CUSTOM_SESSION_POLICY.authenticated_absolute_timeout,
        CUSTOM_SESSION_POLICY.pending_mfa_timeout,
    )

    _rotate(_pending_session(policy=CUSTOM_SESSION_POLICY), policy=CUSTOM_SESSION_POLICY)

    assert (
        CUSTOM_SESSION_POLICY.authenticated_idle_timeout,
        CUSTOM_SESSION_POLICY.authenticated_absolute_timeout,
        CUSTOM_SESSION_POLICY.pending_mfa_timeout,
    ) == before


def test_completion_does_not_mutate_completed_at() -> None:
    completed_at = COMPLETED_AT
    before = completed_at

    _rotate(_pending_session(), completed_at=completed_at)

    assert completed_at is before
    assert completed_at == COMPLETED_AT


def test_rotation_and_transition_symbols_are_importable_from_application() -> None:
    assert AuthenticationSessionRotation.__name__ == "AuthenticationSessionRotation"
    assert AuthenticationSessionTransitionError.__name__ == "AuthenticationSessionTransitionError"


def test_raw_token_absent_from_all_result_repr_strings() -> None:
    rotation = _rotate(_pending_session())

    assert RAW_TOKEN_NEW.value not in repr(rotation)
    assert RAW_TOKEN_NEW.value not in repr(rotation.issued)
    assert RAW_TOKEN_NEW.value not in repr(rotation.revoked_session)
