"""Tests for CLS-011.2f authentication email value object."""

# mypy: disable-error-code=import-untyped

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from closeros.domain import AuthenticationEmail

VALID_EMAIL = "user@example.com"
PLUS_ADDRESS_EMAIL = "user+tag@example.com"
SUBDOMAIN_EMAIL = "user@mail.example.com"


def test_valid_lowercase_email_is_accepted() -> None:
    authentication_email = AuthenticationEmail(value=VALID_EMAIL)

    assert authentication_email.value == VALID_EMAIL


def test_leading_and_trailing_whitespace_are_removed() -> None:
    authentication_email = AuthenticationEmail(value="  user@example.com  ")

    assert authentication_email.value == VALID_EMAIL


def test_uppercase_characters_are_converted_to_lowercase() -> None:
    authentication_email = AuthenticationEmail(value="User@Example.COM")

    assert authentication_email.value == VALID_EMAIL


def test_normalization_combines_stripping_and_lowercase() -> None:
    authentication_email = AuthenticationEmail(value="  User@Example.COM  ")

    assert authentication_email.value == VALID_EMAIL


def test_plus_addressing_is_preserved() -> None:
    authentication_email = AuthenticationEmail(value=PLUS_ADDRESS_EMAIL)

    assert authentication_email.value == PLUS_ADDRESS_EMAIL


def test_subdomains_are_preserved() -> None:
    authentication_email = AuthenticationEmail(value=SUBDOMAIN_EMAIL)

    assert authentication_email.value == SUBDOMAIN_EMAIL


def test_empty_string_raises_value_error() -> None:
    with pytest.raises(ValueError, match="value must not be empty"):
        AuthenticationEmail(value="")


def test_whitespace_only_string_raises_value_error() -> None:
    with pytest.raises(ValueError, match="value must not be empty"):
        AuthenticationEmail(value="   ")


def test_email_without_at_raises_value_error() -> None:
    with pytest.raises(ValueError, match="value must contain exactly one @"):
        AuthenticationEmail(value="userexample.com")


def test_email_with_multiple_at_characters_raises_value_error() -> None:
    with pytest.raises(ValueError, match="value must contain exactly one @"):
        AuthenticationEmail(value="user@mail@example.com")


def test_empty_local_part_raises_value_error() -> None:
    with pytest.raises(ValueError, match="email local part must not be empty"):
        AuthenticationEmail(value="@example.com")


def test_empty_domain_part_raises_value_error() -> None:
    with pytest.raises(ValueError, match="email domain part must not be empty"):
        AuthenticationEmail(value="user@")


def test_whitespace_in_local_part_raises_value_error() -> None:
    with pytest.raises(ValueError, match="value must not contain whitespace"):
        AuthenticationEmail(value="user name@example.com")


def test_whitespace_in_domain_part_raises_value_error() -> None:
    with pytest.raises(ValueError, match="value must not contain whitespace"):
        AuthenticationEmail(value="user@mail example.com")


def test_bytes_raise_type_error() -> None:
    with pytest.raises(TypeError, match="value must be a string"):
        AuthenticationEmail(value=cast(Any, b"user@example.com"))


def test_none_raises_type_error() -> None:
    with pytest.raises(TypeError, match="value must be a string"):
        AuthenticationEmail(value=cast(Any, None))


def test_authentication_email_is_immutable() -> None:
    authentication_email = AuthenticationEmail(value=VALID_EMAIL)

    with pytest.raises(FrozenInstanceError):
        cast(Any, authentication_email).value = "other@example.com"


def test_repr_does_not_contain_email_address() -> None:
    authentication_email_repr = repr(AuthenticationEmail(value=VALID_EMAIL))

    assert VALID_EMAIL not in authentication_email_repr
    assert "user" not in authentication_email_repr
    assert "example.com" not in authentication_email_repr


def test_authentication_email_can_be_imported_from_closeros_domain() -> None:
    assert AuthenticationEmail.__name__ == "AuthenticationEmail"
