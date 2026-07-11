"""Tests for CLS-011.3g authentication issuance application services."""

# mypy: disable-error-code=import-untyped

from base64 import urlsafe_b64encode
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.application import (
    AuthenticationSessionRotation,
    AuthenticationSessionTransitionError,
    IssuedAuthenticationOneTimeToken,
    IssuedAuthenticationSession,
    complete_pending_mfa_and_rotate_session,
    issue_authenticated_session,
    issue_authentication_one_time_token,
    issue_pending_mfa_session,
)
from closeros.application import authentication_issuance as issuance_module
from closeros.domain import (
    AuthenticationAssuranceLevel,
    AuthenticationOneTimeTokenTimeoutPolicy,
    AuthenticationSession,
    AuthenticationSessionStage,
    AuthenticationSessionTimeoutPolicy,
    AuthenticationTokenPurpose,
)
from closeros.security import RawAuthenticationToken, hash_authentication_token

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")
TOKEN_ID = UUID("00000000-0000-0000-0000-000000000003")
NEW_SESSION_ID = UUID("00000000-0000-0000-0000-000000000004")

ISSUED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)

CUSTOM_SESSION_POLICY = AuthenticationSessionTimeoutPolicy(
    authenticated_idle_timeout=timedelta(minutes=7),
    authenticated_absolute_timeout=timedelta(hours=3),
    pending_mfa_timeout=timedelta(minutes=2),
)
CUSTOM_TOKEN_POLICY = AuthenticationOneTimeTokenTimeoutPolicy(
    email_verification_timeout=timedelta(hours=6),
    password_reset_timeout=timedelta(minutes=15),
)


def _raw_token_from_bytes(raw: bytes) -> RawAuthenticationToken:
    return RawAuthenticationToken(urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"))


RAW_TOKEN_A = _raw_token_from_bytes(bytes(range(32)))
RAW_TOKEN_B = _raw_token_from_bytes(bytes(reversed(range(32))))


class RecordingRawTokenFactory:
    def __init__(self, raw_token: RawAuthenticationToken) -> None:
        self._raw_token = raw_token
        self.calls = 0

    def __call__(self) -> RawAuthenticationToken:
        self.calls += 1
        return self._raw_token


def _valid_pending_session() -> AuthenticationSession:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)
    issued = issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )
    return issued.session


def test_issued_authentication_session_accepts_valid_fields() -> None:
    session = _valid_pending_session()

    issued = IssuedAuthenticationSession(session=session, raw_token=RAW_TOKEN_A)

    assert issued.session is session
    assert issued.raw_token is RAW_TOKEN_A


def test_issued_authentication_session_rejects_wrong_session_type() -> None:
    with pytest.raises(TypeError, match="session must be an AuthenticationSession"):
        IssuedAuthenticationSession(
            session=cast(Any, object()),
            raw_token=RAW_TOKEN_A,
        )


def test_issued_authentication_session_rejects_wrong_raw_token_type() -> None:
    session = _valid_pending_session()

    with pytest.raises(TypeError, match="raw_token must be a RawAuthenticationToken"):
        IssuedAuthenticationSession(
            session=session,
            raw_token=cast(Any, RAW_TOKEN_A.value),
        )


def test_issued_authentication_session_is_immutable() -> None:
    session = _valid_pending_session()
    issued = IssuedAuthenticationSession(session=session, raw_token=RAW_TOKEN_A)

    with pytest.raises(FrozenInstanceError):
        cast(Any, issued).raw_token = RAW_TOKEN_B


def test_issued_authentication_session_repr_hides_raw_token() -> None:
    session = _valid_pending_session()
    issued = IssuedAuthenticationSession(session=session, raw_token=RAW_TOKEN_A)

    assert RAW_TOKEN_A.value not in repr(issued)


def _valid_one_time_token() -> IssuedAuthenticationOneTimeToken:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)
    return issue_authentication_one_time_token(
        token_id=TOKEN_ID,
        user_id=USER_ID,
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )


def test_issued_one_time_token_accepts_valid_fields() -> None:
    issued = _valid_one_time_token()

    rebuilt = IssuedAuthenticationOneTimeToken(
        token=issued.token,
        raw_token=RAW_TOKEN_A,
    )

    assert rebuilt.token is issued.token
    assert rebuilt.raw_token is RAW_TOKEN_A


def test_issued_one_time_token_rejects_wrong_token_type() -> None:
    with pytest.raises(TypeError, match="token must be an AuthenticationOneTimeToken"):
        IssuedAuthenticationOneTimeToken(
            token=cast(Any, object()),
            raw_token=RAW_TOKEN_A,
        )


def test_issued_one_time_token_rejects_wrong_raw_token_type() -> None:
    issued = _valid_one_time_token()

    with pytest.raises(TypeError, match="raw_token must be a RawAuthenticationToken"):
        IssuedAuthenticationOneTimeToken(
            token=issued.token,
            raw_token=cast(Any, RAW_TOKEN_A.value),
        )


def test_issued_one_time_token_is_immutable() -> None:
    issued = _valid_one_time_token()

    with pytest.raises(FrozenInstanceError):
        cast(Any, issued).raw_token = RAW_TOKEN_B


def test_issued_one_time_token_repr_hides_raw_token() -> None:
    issued = _valid_one_time_token()

    assert RAW_TOKEN_A.value not in repr(issued)


def test_authentication_session_rotation_validates_both_fields() -> None:
    session = _valid_pending_session()
    issued = IssuedAuthenticationSession(session=session, raw_token=RAW_TOKEN_A)

    with pytest.raises(
        TypeError,
        match="revoked_session must be an AuthenticationSession",
    ):
        AuthenticationSessionRotation(
            revoked_session=cast(Any, object()),
            issued=issued,
        )

    with pytest.raises(
        TypeError,
        match="issued must be an IssuedAuthenticationSession",
    ):
        AuthenticationSessionRotation(
            revoked_session=session,
            issued=cast(Any, object()),
        )


def test_authentication_session_rotation_is_immutable() -> None:
    session = _valid_pending_session()
    issued = IssuedAuthenticationSession(session=session, raw_token=RAW_TOKEN_A)
    rotation = AuthenticationSessionRotation(
        revoked_session=session,
        issued=issued,
    )

    with pytest.raises(FrozenInstanceError):
        cast(Any, rotation).issued = issued


def test_nested_rotation_repr_does_not_expose_raw_token() -> None:
    session = _valid_pending_session()
    issued = IssuedAuthenticationSession(session=session, raw_token=RAW_TOKEN_A)
    rotation = AuthenticationSessionRotation(
        revoked_session=session,
        issued=issued,
    )

    assert RAW_TOKEN_A.value not in repr(rotation)


def test_pending_mfa_issuance_creates_exact_combination() -> None:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)
    issued = issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )

    session = issued.session
    assert session.id == SESSION_ID
    assert session.user_id == USER_ID
    assert session.stage is AuthenticationSessionStage.PENDING_MFA
    assert session.assurance_level is AuthenticationAssuranceLevel.SINGLE_FACTOR
    assert session.mfa_completed is False
    assert session.revoked_at is None


def test_pending_mfa_created_at_and_last_seen_at_equal_issued_at() -> None:
    issued = issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued.session.created_at == ISSUED_AT
    assert issued.session.last_seen_at == ISSUED_AT


def test_pending_mfa_expiry_is_exactly_five_minutes_with_canonical_policy() -> None:
    issued = issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued.session.expires_at == ISSUED_AT + timedelta(minutes=5)


def test_pending_mfa_custom_policy_controls_expiry() -> None:
    issued = issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        timeout_policy=CUSTOM_SESSION_POLICY,
    )

    assert issued.session.expires_at == ISSUED_AT + timedelta(minutes=2)


def test_pending_mfa_token_hash_matches_returned_raw_token() -> None:
    issued = issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued.session.token_hash.digest == hash_authentication_token(issued.raw_token).digest
    assert issued.raw_token is RAW_TOKEN_A


def test_pending_mfa_factory_is_called_exactly_once() -> None:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)

    issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )

    assert factory.calls == 1


def test_authenticated_single_factor_session_is_created_correctly() -> None:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)
    issued = issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )

    session = issued.session
    assert session.stage is AuthenticationSessionStage.AUTHENTICATED
    assert session.assurance_level is AuthenticationAssuranceLevel.SINGLE_FACTOR
    assert session.mfa_completed is False
    assert session.revoked_at is None


def test_authenticated_multi_factor_session_is_created_correctly() -> None:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)
    issued = issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )

    session = issued.session
    assert session.stage is AuthenticationSessionStage.AUTHENTICATED
    assert session.assurance_level is AuthenticationAssuranceLevel.MULTI_FACTOR
    assert session.mfa_completed is True


def test_authenticated_expiry_is_exactly_twelve_hours_with_canonical_policy() -> None:
    issued = issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued.session.expires_at == ISSUED_AT + timedelta(hours=12)


def test_authenticated_custom_policy_controls_expiry() -> None:
    issued = issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        timeout_policy=CUSTOM_SESSION_POLICY,
    )

    assert issued.session.expires_at == ISSUED_AT + timedelta(hours=3)


def test_authenticated_token_hash_matches_returned_raw_token() -> None:
    issued = issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued.session.token_hash.digest == hash_authentication_token(issued.raw_token).digest


def test_authenticated_factory_is_called_exactly_once() -> None:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)

    issue_authenticated_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )

    assert factory.calls == 1


def test_email_verification_token_expiry_is_exactly_24_hours() -> None:
    issued = issue_authentication_one_time_token(
        token_id=TOKEN_ID,
        user_id=USER_ID,
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued.token.expires_at == ISSUED_AT + timedelta(hours=24)


def test_password_reset_token_expiry_is_exactly_30_minutes() -> None:
    issued = issue_authentication_one_time_token(
        token_id=TOKEN_ID,
        user_id=USER_ID,
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued.token.expires_at == ISSUED_AT + timedelta(minutes=30)


def test_custom_token_policy_controls_email_verification_expiry() -> None:
    issued = issue_authentication_one_time_token(
        token_id=TOKEN_ID,
        user_id=USER_ID,
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        timeout_policy=CUSTOM_TOKEN_POLICY,
    )

    assert issued.token.expires_at == ISSUED_AT + timedelta(hours=6)


def test_custom_token_policy_controls_password_reset_expiry() -> None:
    issued = issue_authentication_one_time_token(
        token_id=TOKEN_ID,
        user_id=USER_ID,
        purpose=AuthenticationTokenPurpose.PASSWORD_RESET,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        timeout_policy=CUSTOM_TOKEN_POLICY,
    )

    assert issued.token.expires_at == ISSUED_AT + timedelta(minutes=15)


def test_issued_one_time_token_has_consumed_at_none() -> None:
    issued = _valid_one_time_token()

    assert issued.token.consumed_at is None


def test_issued_one_time_token_has_revoked_at_none() -> None:
    issued = _valid_one_time_token()

    assert issued.token.revoked_at is None


def test_one_time_token_hash_matches_returned_raw_token() -> None:
    issued = _valid_one_time_token()

    assert issued.token.token_hash.digest == hash_authentication_token(issued.raw_token).digest


def test_one_time_token_factory_is_called_exactly_once() -> None:
    factory = RecordingRawTokenFactory(RAW_TOKEN_A)

    issue_authentication_one_time_token(
        token_id=TOKEN_ID,
        user_id=USER_ID,
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        issued_at=ISSUED_AT,
        raw_token_factory=factory,
    )

    assert factory.calls == 1


def test_invalid_session_id_uuid_raises_safe_type_error() -> None:
    with pytest.raises(TypeError, match="session_id must be a UUID"):
        issue_pending_mfa_session(
            session_id=cast(Any, "not-a-uuid"),
            user_id=USER_ID,
            issued_at=ISSUED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        )


def test_invalid_user_id_uuid_raises_safe_type_error() -> None:
    with pytest.raises(TypeError, match="user_id must be a UUID"):
        issue_pending_mfa_session(
            session_id=SESSION_ID,
            user_id=cast(Any, 12345),
            issued_at=ISSUED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        )


def test_invalid_issued_at_type_raises_safe_type_error() -> None:
    with pytest.raises(TypeError, match="issued_at must be a datetime"):
        issue_pending_mfa_session(
            session_id=SESSION_ID,
            user_id=USER_ID,
            issued_at=cast(Any, "2026-07-11T12:00:00Z"),
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        )


def test_naive_issued_at_raises_safe_value_error() -> None:
    with pytest.raises(ValueError, match="issued_at must be timezone-aware"):
        issue_pending_mfa_session(
            session_id=SESSION_ID,
            user_id=USER_ID,
            issued_at=datetime(2026, 7, 11, 12, 0, 0),
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        )


def test_invalid_assurance_type_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="assurance_level must be an AuthenticationAssuranceLevel",
    ):
        issue_authenticated_session(
            session_id=SESSION_ID,
            user_id=USER_ID,
            assurance_level=cast(Any, "multi_factor"),
            issued_at=ISSUED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        )


def test_invalid_purpose_type_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="purpose must be an AuthenticationTokenPurpose",
    ):
        issue_authentication_one_time_token(
            token_id=TOKEN_ID,
            user_id=USER_ID,
            purpose=cast(Any, "email_verification"),
            issued_at=ISSUED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        )


def test_invalid_session_timeout_policy_type_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="timeout_policy must be an AuthenticationSessionTimeoutPolicy",
    ):
        issue_pending_mfa_session(
            session_id=SESSION_ID,
            user_id=USER_ID,
            issued_at=ISSUED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
            timeout_policy=cast(Any, object()),
        )


def test_invalid_one_time_token_timeout_policy_type_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="timeout_policy must be an AuthenticationOneTimeTokenTimeoutPolicy",
    ):
        issue_authentication_one_time_token(
            token_id=TOKEN_ID,
            user_id=USER_ID,
            purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
            issued_at=ISSUED_AT,
            raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
            timeout_policy=cast(Any, object()),
        )


def test_non_callable_raw_token_factory_raises_type_error() -> None:
    with pytest.raises(TypeError, match="raw_token_factory must be callable"):
        issue_pending_mfa_session(
            session_id=SESSION_ID,
            user_id=USER_ID,
            issued_at=ISSUED_AT,
            raw_token_factory=cast(Any, object()),
        )


def test_factory_returning_wrong_type_raises_type_error() -> None:
    with pytest.raises(
        TypeError,
        match="raw_token_factory must return a RawAuthenticationToken",
    ):
        issue_pending_mfa_session(
            session_id=SESSION_ID,
            user_id=USER_ID,
            issued_at=ISSUED_AT,
            raw_token_factory=cast(Any, lambda: "not-a-token"),
        )


def test_issuance_does_not_mutate_supplied_datetime() -> None:
    issued_at = ISSUED_AT
    before = issued_at

    issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=issued_at,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
    )

    assert issued_at is before
    assert issued_at == ISSUED_AT


def test_issuance_does_not_mutate_supplied_timeout_policies() -> None:
    session_before = (
        CUSTOM_SESSION_POLICY.authenticated_idle_timeout,
        CUSTOM_SESSION_POLICY.authenticated_absolute_timeout,
        CUSTOM_SESSION_POLICY.pending_mfa_timeout,
    )
    token_before = (
        CUSTOM_TOKEN_POLICY.email_verification_timeout,
        CUSTOM_TOKEN_POLICY.password_reset_timeout,
    )

    issue_pending_mfa_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        timeout_policy=CUSTOM_SESSION_POLICY,
    )
    issue_authentication_one_time_token(
        token_id=TOKEN_ID,
        user_id=USER_ID,
        purpose=AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        issued_at=ISSUED_AT,
        raw_token_factory=RecordingRawTokenFactory(RAW_TOKEN_A),
        timeout_policy=CUSTOM_TOKEN_POLICY,
    )

    assert (
        CUSTOM_SESSION_POLICY.authenticated_idle_timeout,
        CUSTOM_SESSION_POLICY.authenticated_absolute_timeout,
        CUSTOM_SESSION_POLICY.pending_mfa_timeout,
    ) == session_before
    assert (
        CUSTOM_TOKEN_POLICY.email_verification_timeout,
        CUSTOM_TOKEN_POLICY.password_reset_timeout,
    ) == token_before


def test_public_issuance_symbols_are_importable_from_application() -> None:
    assert issue_pending_mfa_session.__name__ == "issue_pending_mfa_session"
    assert issue_authenticated_session.__name__ == "issue_authenticated_session"
    assert issue_authentication_one_time_token.__name__ == "issue_authentication_one_time_token"
    assert (
        complete_pending_mfa_and_rotate_session.__name__
        == "complete_pending_mfa_and_rotate_session"
    )
    assert IssuedAuthenticationSession.__name__ == "IssuedAuthenticationSession"
    assert IssuedAuthenticationOneTimeToken.__name__ == "IssuedAuthenticationOneTimeToken"
    assert AuthenticationSessionRotation.__name__ == "AuthenticationSessionRotation"
    assert AuthenticationSessionTransitionError.__name__ == "AuthenticationSessionTransitionError"


def test_private_helpers_and_alias_absent_from_application_all() -> None:
    from closeros import application

    assert "_validate_uuid" not in application.__all__
    assert "_validate_timezone_aware_datetime" not in application.__all__
    assert "_generate_raw_token_and_hash" not in application.__all__
    assert "_RawAuthenticationTokenFactory" not in application.__all__


def test_issuance_module_exposes_expected_all() -> None:
    assert issuance_module.__all__ == application_all()


def application_all() -> list[str]:
    return [
        "AuthenticationSessionRotation",
        "AuthenticationSessionTransitionError",
        "IssuedAuthenticationOneTimeToken",
        "IssuedAuthenticationSession",
        "complete_pending_mfa_and_rotate_session",
        "issue_authenticated_session",
        "issue_authentication_one_time_token",
        "issue_pending_mfa_session",
    ]
