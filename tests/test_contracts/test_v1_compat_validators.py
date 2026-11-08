"""Golden contracts for the validators ported from pydantic 1.9.

``UserInUpdate.image`` uses ``HttpUrlStr``, a port of pydantic 1.9's
``HttpUrl`` validation, and the user emails use ``Email``, which restores
email-validator 1.x's 64-character local-part limit. Every expected value
below was recorded by sending the same request to the pre-upgrade API
(pydantic 1.9.2, email-validator 1.1.3).
"""
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

pytestmark = pytest.mark.asyncio

LOCAL_PART_64 = "{0}@example.com".format("x" * 64)
LOCAL_PART_65 = "{0}@example.com".format("x" * 65)
LOCAL_PART_66 = "{0}@example.com".format("x" * 66)


def _errors(body: Any) -> List[Any]:
    assert list(body) == ["errors"]
    assert isinstance(body["errors"], list)
    return body["errors"]


def _image_error(msg: str, error_type: str, **ctx: Any) -> List[Dict[str, Any]]:
    error: Dict[str, Any] = {
        "loc": ["body", "user", "image"],
        "msg": msg,
        "type": error_type,
    }
    if ctx:
        error["ctx"] = ctx
    return [error]


EMAIL_ERROR = [
    {
        "loc": ["body", "user", "email"],
        "msg": "value is not a valid email address",
        "type": "value_error.email",
    }
]
SCHEME_ERROR = _image_error("invalid or missing URL scheme", "value_error.url.scheme")
STR_ERROR = _image_error("str type expected", "type_error.str")
MIN_LENGTH_ERROR = _image_error(
    "ensure this value has at least 1 characters",
    "value_error.any_str.min_length",
    limit_value=1,
)
HOST_ERROR = _image_error("URL host invalid", "value_error.url.host")
IDNA_ERROR = _image_error(
    "encoding with 'idna' codec failed (UnicodeError: label empty or too long)",
    "value_error.unicode",
)


@pytest.mark.parametrize(
    "image, expected_errors",
    (
        # pydantic-v1 contract: numbers are coerced to str, then fail the scheme check
        (123, SCHEME_ERROR),
        (1.5, SCHEME_ERROR),
        (True, SCHEME_ERROR),
        # pydantic-v1 contract
        (["x"], STR_ERROR),
        ({"a": 1}, STR_ERROR),
        # pydantic-v1 contract: whitespace is stripped before the length check
        ("", MIN_LENGTH_ERROR),
        ("   ", MIN_LENGTH_ERROR),
        # pydantic-v1 contract
        (
            "http://example.com:65536",
            _image_error(
                "URL port invalid, port cannot exceed 65535", "value_error.url.port"
            ),
        ),
        # pydantic-v1 contract
        ("http://-a.com", HOST_ERROR),
        # pydantic-v1 contract
        (
            "http://localhost",
            _image_error(
                "URL host invalid, top level domain required", "value_error.url.host"
            ),
        ),
        # pydantic-v1 contract: a 64-char label fails the host pattern
        ("http://{0}.com".format("ü" * 64), HOST_ERROR),
        # pydantic-v1 contract: a 63-char label passes it but is too long for IDNA
        ("http://{0}.com".format("ü" * 63), IDNA_ERROR),
        ("http://\u00ad.com", IDNA_ERROR),
        # pydantic-v1 contract
        (
            "http://example.com/a b",
            _image_error(
                "URL invalid, extra characters found after valid URL: ' b'",
                "value_error.url.extra",
                extra=" b",
            ),
        ),
    ),
)
async def test_user_update_image_422(
    app: FastAPI,
    authorized_client: AsyncClient,
    image: Any,
    expected_errors: List[Dict[str, Any]],
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"), json={"user": {"image": image}}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert _errors(response.json()) == expected_errors


@pytest.mark.parametrize(
    "image, stored_image",
    (
        # pydantic-v1 contract: ASCII hosts are stored exactly as sent
        ("http://example.com:65535/x", "http://example.com:65535/x"),
        ("http://1.2.3.4/x", "http://1.2.3.4/x"),
        ("http://[::1]:8080/x", "http://[::1]:8080/x"),
        ("https://xn--mnchen-3ya.de/Pic.PNG", "https://xn--mnchen-3ya.de/Pic.PNG"),
        (" https://Example.com/x ", "https://Example.com/x"),
        ("https://ex_am.com/", "https://ex_am.com/"),
        # pydantic-v1 contract: international hosts are rebuilt with punycode
        ("http://münchen.de", "http://xn--mnchen-3ya.de"),
        (
            "https://user:pw@münchen.de:8443/p?q=1#f",
            "https://user:pw@xn--mnchen-3ya.de:8443/p?q=1#f",
        ),
        ("http://üa.\u0640\u0640.com", "http://xn--a-dha.xn--chba.com"),
        # Current behaviour that looks like a bug: the rebuild drops the default
        # port and silently removes a zero-width joiner from the host, but the
        # default-port check is case-sensitive, so "HTTP://...:80" keeps ":80".
        ("http://user@münchen.de:80/", "http://user@xn--mnchen-3ya.de/"),
        ("HTTP://münchen.de:80", "HTTP://xn--mnchen-3ya.de:80"),
        ("http://a\u200d.de", "http://a.de"),
    ),
)
async def test_user_update_image_is_stored_as_v1_string(
    app: FastAPI,
    authorized_client: AsyncClient,
    image: str,
    stored_image: str,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"), json={"user": {"image": image}}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user"]["image"] == stored_image

    response = await authorized_client.get(app.url_path_for("users:get-current-user"))

    assert response.json()["user"]["image"] == stored_image


@pytest.mark.parametrize(
    "route_name, user",
    (
        ("users:update-current-user", {"email": LOCAL_PART_65}),
        ("users:update-current-user", {"email": LOCAL_PART_66}),
        (
            "auth:register",
            {"email": LOCAL_PART_65, "username": "u65", "password": "p"},
        ),
        (
            "auth:register",
            {"email": LOCAL_PART_66, "username": "u66", "password": "p"},
        ),
        ("auth:login", {"email": LOCAL_PART_65, "password": "p"}),
    ),
)
async def test_email_local_part_over_64_chars_is_422(
    app: FastAPI,
    authorized_client: AsyncClient,
    route_name: str,
    user: Dict[str, str],
) -> None:
    method = "PUT" if route_name == "users:update-current-user" else "POST"
    response = await authorized_client.request(
        method, app.url_path_for(route_name), json={"user": user}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert _errors(response.json()) == EMAIL_ERROR


async def test_user_update_accepts_64_char_email_local_part(
    app: FastAPI, authorized_client: AsyncClient
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {"email": LOCAL_PART_64}},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user"]["email"] == LOCAL_PART_64


async def test_registration_accepts_64_char_email_local_part(
    app: FastAPI, client: AsyncClient
) -> None:
    response = await client.post(
        app.url_path_for("auth:register"),
        json={"user": {"email": LOCAL_PART_64, "username": "u64", "password": "p"}},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["user"]["email"] == LOCAL_PART_64


async def test_login_with_64_char_email_local_part_reaches_auth(
    app: FastAPI, client: AsyncClient
) -> None:
    response = await client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": LOCAL_PART_64, "password": "p"}},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"errors": ["incorrect email or password"]}
