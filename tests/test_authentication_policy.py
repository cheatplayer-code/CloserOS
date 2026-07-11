"""Tests for CLS-011.2h privileged-role MFA policy guard."""

# mypy: disable-error-code=import-untyped

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from closeros.domain import (
    AuthenticationAssuranceLevel,
    AuthenticationSession,
    AuthenticationSessionStage,
    AuthenticationTokenHash,
    Membership,
    MfaRequiredError,
    require_privileged_mfa,
    requires_mfa_for_roles,
)
from closeros.domain.identity import MembershipStatus, Role

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000020")
SESSION_ID = UUID("00000000-0000-0000-0000-000000000100")
USER_ID = UUID("00000000-0000-0000-0000-000000000010")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000011")
TOKEN_HASH = AuthenticationTokenHash(digest=bytes(range(32)))
CREATED_AT = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
LAST_SEEN_AT = datetime(2026, 7, 11, 12, 15, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 7, 12, 0, 0, 0, tzinfo=UTC)
DENIED_MESSAGE = "multi-factor authentication required"
SUPPLIED_UUID_STRINGS = (
    str(TENANT_ID),
    str(MEMBERSHIP_ID),
    str(SESSION_ID),
    str(USER_ID),
    str(OTHER_USER_ID),
)


def _build_membership(
    *,
    roles: frozenset[Role],
    user_id: UUID = USER_ID,
) -> Membership:
    return Membership(
        id=MEMBERSHIP_ID,
        tenant_id=TENANT_ID,
        user_id=user_id,
        roles=roles,
        status=MembershipStatus.ACTIVE,
    )


def _build_session(**overrides: object) -> AuthenticationSession:
    values = {
        "id": SESSION_ID,
        "user_id": USER_ID,
        "token_hash": TOKEN_HASH,
        "stage": AuthenticationSessionStage.AUTHENTICATED,
        "assurance_level": AuthenticationAssuranceLevel.MULTI_FACTOR,
        "mfa_completed": True,
        "created_at": CREATED_AT,
        "last_seen_at": LAST_SEEN_AT,
        "expires_at": EXPIRES_AT,
        "revoked_at": None,
    }
    values.update(overrides)
    return AuthenticationSession(**cast(Any, values))


def test_owner_requires_mfa() -> None:
    assert requires_mfa_for_roles(frozenset({Role.OWNER})) is True


def test_sales_head_requires_mfa() -> None:
    assert requires_mfa_for_roles(frozenset({Role.SALES_HEAD})) is True


def test_compliance_admin_requires_mfa() -> None:
    assert requires_mfa_for_roles(frozenset({Role.COMPLIANCE_ADMIN})) is True


def test_manager_does_not_require_mfa() -> None:
    assert requires_mfa_for_roles(frozenset({Role.MANAGER})) is False


def test_analyst_does_not_require_mfa() -> None:
    assert requires_mfa_for_roles(frozenset({Role.ANALYST})) is False


def test_empty_frozenset_does_not_require_mfa() -> None:
    assert requires_mfa_for_roles(frozenset()) is False


def test_mixed_frozenset_containing_manager_and_owner_requires_mfa() -> None:
    assert requires_mfa_for_roles(frozenset({Role.MANAGER, Role.OWNER})) is True


def test_normal_set_instead_of_frozenset_raises_type_error() -> None:
    with pytest.raises(TypeError, match="roles must be a frozenset"):
        requires_mfa_for_roles(cast(Any, {Role.OWNER}))


def test_frozenset_containing_string_raises_type_error() -> None:
    with pytest.raises(TypeError, match="roles must contain only Role values"):
        requires_mfa_for_roles(cast(Any, frozenset({Role.OWNER, "not-a-role"})))


def test_non_privileged_membership_with_single_factor_incomplete_session_is_allowed() -> None:
    membership = _build_membership(roles=frozenset({Role.MANAGER}))
    session = _build_session(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    require_privileged_mfa(membership=membership, session=session)


def test_privileged_membership_with_multi_factor_and_mfa_completed_true_is_allowed() -> None:
    membership = _build_membership(roles=frozenset({Role.OWNER}))
    session = _build_session(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        mfa_completed=True,
    )

    require_privileged_mfa(membership=membership, session=session)


def test_privileged_membership_with_single_factor_and_mfa_completed_false_is_denied() -> None:
    membership = _build_membership(roles=frozenset({Role.OWNER}))
    session = _build_session(
        stage=AuthenticationSessionStage.PENDING_MFA,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    with pytest.raises(MfaRequiredError, match=f"^{DENIED_MESSAGE}$"):
        require_privileged_mfa(membership=membership, session=session)


def test_privileged_membership_with_single_factor_and_mfa_completed_true_is_denied() -> None:
    membership = _build_membership(roles=frozenset({Role.OWNER}))
    session = _build_session(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )
    session.mfa_completed = True

    with pytest.raises(MfaRequiredError, match=f"^{DENIED_MESSAGE}$"):
        require_privileged_mfa(membership=membership, session=session)


def test_privileged_membership_with_multi_factor_and_mfa_completed_false_is_denied() -> None:
    membership = _build_membership(roles=frozenset({Role.OWNER}))
    session = _build_session(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        assurance_level=AuthenticationAssuranceLevel.MULTI_FACTOR,
        mfa_completed=True,
    )
    session.mfa_completed = False

    with pytest.raises(MfaRequiredError, match=f"^{DENIED_MESSAGE}$"):
        require_privileged_mfa(membership=membership, session=session)


def test_mismatched_membership_user_id_and_session_user_id_is_denied() -> None:
    membership = _build_membership(roles=frozenset({Role.MANAGER}))
    session = _build_session(user_id=OTHER_USER_ID)

    with pytest.raises(MfaRequiredError, match=f"^{DENIED_MESSAGE}$"):
        require_privileged_mfa(membership=membership, session=session)


def test_mixed_role_membership_with_privileged_role_denied_without_mfa() -> None:
    membership = _build_membership(roles=frozenset({Role.MANAGER, Role.SALES_HEAD}))
    session = _build_session(
        stage=AuthenticationSessionStage.PENDING_MFA,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    with pytest.raises(MfaRequiredError, match=f"^{DENIED_MESSAGE}$"):
        require_privileged_mfa(membership=membership, session=session)


@pytest.mark.parametrize(
    "roles",
    [
        frozenset({Role.OWNER}),
        frozenset({Role.SALES_HEAD}),
        frozenset({Role.COMPLIANCE_ADMIN}),
        frozenset({Role.MANAGER, Role.OWNER}),
    ],
)
def test_every_denial_raises_mfa_required_error(roles: frozenset[Role]) -> None:
    membership = _build_membership(roles=roles)
    session = _build_session(
        stage=AuthenticationSessionStage.PENDING_MFA,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    with pytest.raises(MfaRequiredError):
        require_privileged_mfa(membership=membership, session=session)


@pytest.mark.parametrize(
    "roles",
    [
        frozenset({Role.OWNER}),
        frozenset({Role.SALES_HEAD}),
        frozenset({Role.COMPLIANCE_ADMIN}),
        frozenset({Role.MANAGER, Role.OWNER}),
    ],
)
def test_every_denial_uses_exact_denial_message(roles: frozenset[Role]) -> None:
    membership = _build_membership(roles=roles)
    session = _build_session(
        stage=AuthenticationSessionStage.PENDING_MFA,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    with pytest.raises(MfaRequiredError, match=f"^{DENIED_MESSAGE}$") as exc_info:
        require_privileged_mfa(membership=membership, session=session)

    assert str(exc_info.value) == DENIED_MESSAGE


def test_denial_repr_and_message_contain_none_of_supplied_uuid_strings() -> None:
    membership = _build_membership(roles=frozenset({Role.OWNER}))
    session = _build_session(
        stage=AuthenticationSessionStage.PENDING_MFA,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )

    with pytest.raises(MfaRequiredError) as exc_info:
        require_privileged_mfa(membership=membership, session=session)

    error_text = f"{exc_info.value}{repr(exc_info.value)}"
    for uuid_string in SUPPLIED_UUID_STRINGS:
        assert uuid_string not in error_text


def test_wrong_membership_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="membership must be a Membership"):
        require_privileged_mfa(
            membership=cast(Any, object()),
            session=_build_session(),
        )


def test_wrong_session_argument_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="session must be an AuthenticationSession"):
        require_privileged_mfa(
            membership=_build_membership(roles=frozenset({Role.MANAGER})),
            session=cast(Any, object()),
        )


def test_policy_does_not_mutate_membership() -> None:
    membership = _build_membership(roles=frozenset({Role.MANAGER}))
    before = (
        membership.id,
        membership.tenant_id,
        membership.user_id,
        membership.roles,
        membership.status,
    )

    require_privileged_mfa(
        membership=membership,
        session=_build_session(
            stage=AuthenticationSessionStage.AUTHENTICATED,
            assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
            mfa_completed=False,
        ),
    )

    after = (
        membership.id,
        membership.tenant_id,
        membership.user_id,
        membership.roles,
        membership.status,
    )
    assert after == before


def test_policy_does_not_mutate_authentication_session() -> None:
    membership = _build_membership(roles=frozenset({Role.MANAGER}))
    session = _build_session(
        stage=AuthenticationSessionStage.AUTHENTICATED,
        assurance_level=AuthenticationAssuranceLevel.SINGLE_FACTOR,
        mfa_completed=False,
    )
    before = (
        session.id,
        session.user_id,
        session.token_hash,
        session.stage,
        session.assurance_level,
        session.mfa_completed,
        session.created_at,
        session.last_seen_at,
        session.expires_at,
        session.revoked_at,
    )

    require_privileged_mfa(membership=membership, session=session)

    after = (
        session.id,
        session.user_id,
        session.token_hash,
        session.stage,
        session.assurance_level,
        session.mfa_completed,
        session.created_at,
        session.last_seen_at,
        session.expires_at,
        session.revoked_at,
    )
    assert after == before


def test_policy_symbols_can_be_imported_from_closeros_domain() -> None:
    assert MfaRequiredError.__name__ == "MfaRequiredError"
    assert requires_mfa_for_roles.__name__ == "requires_mfa_for_roles"
    assert require_privileged_mfa.__name__ == "require_privileged_mfa"
