"""Tests for CLS-011.2a authentication core enums."""

# mypy: disable-error-code=import-untyped

from enum import StrEnum

from closeros.domain import (
    AuthenticationAssuranceLevel,
    AuthenticationTokenPurpose,
    MfaMethod,
)

_AUTHENTICATION_ENUMS: tuple[type[StrEnum], ...] = (
    AuthenticationAssuranceLevel,
    MfaMethod,
    AuthenticationTokenPurpose,
)


def test_authentication_assurance_level_exact_values() -> None:
    assert AuthenticationAssuranceLevel.SINGLE_FACTOR.value == "single_factor"
    assert AuthenticationAssuranceLevel.MULTI_FACTOR.value == "multi_factor"
    assert set(AuthenticationAssuranceLevel) == {
        AuthenticationAssuranceLevel.SINGLE_FACTOR,
        AuthenticationAssuranceLevel.MULTI_FACTOR,
    }


def test_mfa_method_exact_values() -> None:
    assert MfaMethod.WEBAUTHN.value == "webauthn"
    assert MfaMethod.TOTP.value == "totp"
    assert set(MfaMethod) == {MfaMethod.WEBAUTHN, MfaMethod.TOTP}


def test_authentication_token_purpose_exact_values() -> None:
    assert AuthenticationTokenPurpose.EMAIL_VERIFICATION.value == "email_verification"
    assert AuthenticationTokenPurpose.PASSWORD_RESET.value == "password_reset"
    assert set(AuthenticationTokenPurpose) == {
        AuthenticationTokenPurpose.EMAIL_VERIFICATION,
        AuthenticationTokenPurpose.PASSWORD_RESET,
    }


def test_enum_members_behave_as_strings() -> None:
    for enum_cls in _AUTHENTICATION_ENUMS:
        for member in enum_cls:
            assert isinstance(member, str)
            assert str(member) == member.value


def test_enum_values_are_unique() -> None:
    for enum_cls in _AUTHENTICATION_ENUMS:
        values = [member.value for member in enum_cls]
        assert len(values) == len(set(values))


def test_sms_is_not_present_as_mfa_method() -> None:
    assert "sms" not in {member.value for member in MfaMethod}


def test_authentication_enums_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationAssuranceLevel.__name__ == "AuthenticationAssuranceLevel"
    assert MfaMethod.__name__ == "MfaMethod"
    assert AuthenticationTokenPurpose.__name__ == "AuthenticationTokenPurpose"
