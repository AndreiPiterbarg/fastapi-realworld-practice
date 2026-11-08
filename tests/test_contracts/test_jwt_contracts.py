import time
from datetime import timedelta

import jwt as pyjwt
import pytest

from app.models.domain.users import User
from app.services.jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    JWT_SUBJECT,
    create_access_token_for_user,
    create_jwt_token,
    get_username_from_token,
)

SECRET = "contract-secret"
USER = User(username="contract-user", email="contract@test.com")


def test_constants() -> None:
    assert (JWT_SUBJECT, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES) == (
        "access",
        "HS256",
        10080,
    )


def test_access_token_header() -> None:
    token = create_access_token_for_user(USER, SECRET)

    assert pyjwt.get_unverified_header(token) == {"typ": "JWT", "alg": "HS256"}


def test_access_token_payload() -> None:
    before = int(time.time())
    token = create_access_token_for_user(USER, SECRET)
    after = int(time.time())

    payload = pyjwt.decode(token, SECRET, algorithms=["HS256"])

    assert sorted(payload) == ["exp", "sub", "username"]
    assert payload["username"] == "contract-user"
    assert payload["sub"] == "access"
    assert isinstance(payload["exp"], int)
    week = 7 * 24 * 60 * 60
    assert before + week - 1 <= payload["exp"] <= after + week + 1


def test_round_trip() -> None:
    token = create_access_token_for_user(USER, SECRET)

    assert get_username_from_token(token, SECRET) == "contract-user"


def test_content_is_not_mutated() -> None:
    content = {"username": "u"}

    create_jwt_token(jwt_content=content, secret_key=SECRET, expires_delta=timedelta(1))

    assert content == {"username": "u"}


def test_expired_token() -> None:
    token = create_jwt_token(
        jwt_content={"username": "u"},
        secret_key=SECRET,
        expires_delta=timedelta(minutes=-1),
    )

    with pytest.raises(ValueError, match="^unable to decode JWT token$") as exc_info:
        get_username_from_token(token, SECRET)

    assert isinstance(exc_info.value.__cause__, pyjwt.ExpiredSignatureError)


def test_wrong_secret() -> None:
    token = create_access_token_for_user(USER, SECRET)

    with pytest.raises(ValueError, match="^unable to decode JWT token$") as exc_info:
        get_username_from_token(token, "other-secret")

    assert isinstance(exc_info.value.__cause__, pyjwt.InvalidSignatureError)


def test_garbage_token() -> None:
    with pytest.raises(ValueError, match="^unable to decode JWT token$"):
        get_username_from_token("not.a.jwt", SECRET)


def test_missing_username_claim() -> None:
    token = create_jwt_token(
        jwt_content={"name": "u"},
        secret_key=SECRET,
        expires_delta=timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="^malformed payload in token$"):
        get_username_from_token(token, SECRET)


def test_token_without_exp_is_accepted() -> None:
    # Current behaviour: exp is not a required claim on decode.
    token = pyjwt.encode({"username": "u"}, SECRET, algorithm="HS256")

    assert get_username_from_token(token, SECRET) == "u"


def test_subject_is_not_checked() -> None:
    # Current behaviour that looks like a bug: any "sub" is accepted.
    token = pyjwt.encode({"username": "u", "sub": "refresh"}, SECRET, algorithm="HS256")

    assert get_username_from_token(token, SECRET) == "u"


def test_other_algorithm_is_rejected() -> None:
    token = pyjwt.encode({"username": "u"}, SECRET, algorithm="HS512")

    with pytest.raises(ValueError, match="^unable to decode JWT token$"):
        get_username_from_token(token, SECRET)
