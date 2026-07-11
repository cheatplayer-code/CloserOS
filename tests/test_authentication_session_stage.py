"""Tests for CLS-011.3a authentication session stage enum."""

# mypy: disable-error-code=import-untyped

from enum import StrEnum

from closeros.domain import AuthenticationSessionStage

_UNEXPECTED_VALUES = (
    "password_reset",
    "logged_out",
    "expired",
    "revoked",
)


def test_pending_mfa_value_equals_pending_mfa() -> None:
    assert AuthenticationSessionStage.PENDING_MFA.value == "pending_mfa"


def test_authenticated_value_equals_authenticated() -> None:
    assert AuthenticationSessionStage.AUTHENTICATED.value == "authenticated"


def test_enum_contains_exactly_two_members() -> None:
    assert set(AuthenticationSessionStage) == {
        AuthenticationSessionStage.PENDING_MFA,
        AuthenticationSessionStage.AUTHENTICATED,
    }


def test_every_member_is_a_str() -> None:
    for member in AuthenticationSessionStage:
        assert isinstance(member, str)


def test_str_member_equals_member_value() -> None:
    for member in AuthenticationSessionStage:
        assert str(member) == member.value


def test_values_are_unique() -> None:
    values = [member.value for member in AuthenticationSessionStage]
    assert len(values) == len(set(values))


def test_no_unexpected_values() -> None:
    actual_values = {member.value for member in AuthenticationSessionStage}
    for unexpected_value in _UNEXPECTED_VALUES:
        assert unexpected_value not in actual_values


def test_authentication_session_stage_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationSessionStage.__name__ == "AuthenticationSessionStage"
    assert issubclass(AuthenticationSessionStage, StrEnum)
