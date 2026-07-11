"""Cryptographically secure authentication token generation and hashing."""

from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64DecodeError
from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest
from secrets import token_bytes

from closeros.domain.authentication import AuthenticationTokenHash

_TOKEN_ENTROPY_BYTES = 32
_ENCODED_TOKEN_LENGTH = 43
_URLSAFE_TOKEN_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


@dataclass(frozen=True, slots=True)
class RawAuthenticationToken:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise TypeError("value must be a string")

        if len(self.value) != _ENCODED_TOKEN_LENGTH:
            raise ValueError("value must be a canonical URL-safe encoding of exactly 32 bytes")

        if any(character not in _URLSAFE_TOKEN_CHARACTERS for character in self.value):
            raise ValueError("value must be a canonical URL-safe encoding of exactly 32 bytes")

        padded_value = f"{self.value}="

        try:
            decoded_value = b64decode(
                padded_value,
                altchars=b"-_",
                validate=True,
            )
        except (Base64DecodeError, ValueError) as error:
            raise ValueError(
                "value must be a canonical URL-safe encoding of exactly 32 bytes"
            ) from error

        canonical_value = urlsafe_b64encode(decoded_value).rstrip(b"=").decode("ascii")

        if len(decoded_value) != _TOKEN_ENTROPY_BYTES or canonical_value != self.value:
            raise ValueError("value must be a canonical URL-safe encoding of exactly 32 bytes")


def generate_raw_authentication_token() -> RawAuthenticationToken:
    random_bytes = token_bytes(_TOKEN_ENTROPY_BYTES)
    encoded_value = urlsafe_b64encode(random_bytes).rstrip(b"=").decode("ascii")
    return RawAuthenticationToken(encoded_value)


def hash_authentication_token(
    token: RawAuthenticationToken,
) -> AuthenticationTokenHash:
    if not isinstance(token, RawAuthenticationToken):
        raise TypeError("token must be a RawAuthenticationToken")

    digest = sha256(token.value.encode("ascii")).digest()
    return AuthenticationTokenHash(digest=digest)


def authentication_token_matches_hash(
    *,
    token: RawAuthenticationToken,
    expected_hash: AuthenticationTokenHash,
) -> bool:
    if not isinstance(token, RawAuthenticationToken):
        raise TypeError("token must be a RawAuthenticationToken")

    if not isinstance(expected_hash, AuthenticationTokenHash):
        raise TypeError("expected_hash must be an AuthenticationTokenHash")

    candidate_hash = hash_authentication_token(token)

    return compare_digest(
        candidate_hash.digest,
        expected_hash.digest,
    )
