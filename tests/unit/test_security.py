"""T003 — password hashing vs. token hashing are distinct primitives (R-6).

Unexecuted (no Python in the authoring environment). No DB required.
"""

import hashlib

from app.core.security import hash_password, hash_token, verify_password


def test_hash_password_is_salted_and_verifiable():
    first = hash_password("s3cret")
    second = hash_password("s3cret")

    assert first != "s3cret"
    assert first != second  # bcrypt salts every call
    assert verify_password("s3cret", first)
    assert verify_password("s3cret", second)
    assert not verify_password("wrong", first)


def test_verify_password_tolerates_a_malformed_hash():
    assert not verify_password("s3cret", "not-a-bcrypt-hash")


def test_hash_token_is_a_64_char_sha256_hex_digest():
    digest = hash_token("some-opaque-refresh-token")

    assert digest == hashlib.sha256(b"some-opaque-refresh-token").hexdigest()
    assert len(digest) == 64  # fits refresh_token.token_hash String(64)


def test_hash_token_is_deterministic_but_unlike_the_password_hash():
    # Deterministic: required, since refresh tokens are looked up by hash.
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
    # And it is emphatically not the password scheme.
    assert not hash_token("abc").startswith("$2")
