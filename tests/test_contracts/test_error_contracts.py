"""Golden contracts for error responses.

Error bodies are part of the wire contract with the mobile clients. Entries
marked ``# pydantic-v1 contract`` hold pydantic-1.9 validation output
(``loc``/``msg``/``type``/``ctx``). Pydantic v2 produces different output by
default, so the migration has to keep this output (for example with a
compatibility shim in the 422 handler). It must not change these expectations.
"""
from datetime import timedelta
from os import environ
from typing import Any, Callable, Dict, List

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.models.domain.articles import Article
from app.models.domain.users import User, UserInDB
from app.resources import strings
from app.services import jwt
from tests.test_contracts.conftest import make_token

pytestmark = pytest.mark.asyncio


def _errors(body: Any) -> List[Any]:
    assert list(body) == ["errors"]
    assert isinstance(body["errors"], list)
    return body["errors"]


# --- HTTPException envelope -------------------------------------------------


@pytest.mark.parametrize(
    "method, path, expected_status, detail",
    (
        ("GET", "/api/articles/missing", 404, strings.ARTICLE_DOES_NOT_EXIST_ERROR),
        ("GET", "/api/profiles/nobody", 404, strings.USER_DOES_NOT_EXIST_ERROR),
        (
            "GET",
            "/api/articles/missing/comments",
            404,
            strings.ARTICLE_DOES_NOT_EXIST_ERROR,
        ),
        ("GET", "/api/user", 403, strings.AUTHENTICATION_REQUIRED),
        ("GET", "/api/articles/feed", 403, strings.AUTHENTICATION_REQUIRED),
        ("POST", "/api/articles", 403, strings.AUTHENTICATION_REQUIRED),
        ("GET", "/api/does-not-exist", 404, "Not Found"),
        ("PATCH", "/api/articles", 405, "Method Not Allowed"),
    ),
)
async def test_http_error_envelope(
    client: AsyncClient,
    method: str,
    path: str,
    expected_status: int,
    detail: str,
) -> None:
    response = await client.request(method, path)

    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"errors": [detail]}


async def test_missing_auth_is_403_never_401(app: FastAPI, client: AsyncClient) -> None:
    # Current behaviour: APIKeyHeader yields 403 and nothing in the app emits 401.
    response = await client.put(app.url_path_for("users:update-current-user"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"errors": [strings.AUTHENTICATION_REQUIRED]}


# --- 422 validation envelope ------------------------------------------------


@pytest.mark.parametrize(
    "path, expected_errors",
    (
        (
            "/api/articles?limit=0",
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["query", "limit"],
                    "msg": "ensure this value is greater than or equal to 1",
                    "type": "value_error.number.not_ge",
                    "ctx": {"limit_value": 1},
                }
            ],
        ),
        (
            "/api/articles?offset=-1",
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["query", "offset"],
                    "msg": "ensure this value is greater than or equal to 0",
                    "type": "value_error.number.not_ge",
                    "ctx": {"limit_value": 0},
                }
            ],
        ),
        (
            "/api/articles?limit=0&offset=-1",
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["query", "limit"],
                    "msg": "ensure this value is greater than or equal to 1",
                    "type": "value_error.number.not_ge",
                    "ctx": {"limit_value": 1},
                },
                {
                    "loc": ["query", "offset"],
                    "msg": "ensure this value is greater than or equal to 0",
                    "type": "value_error.number.not_ge",
                    "ctx": {"limit_value": 0},
                },
            ],
        ),
        (
            "/api/articles?limit=abc",
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["query", "limit"],
                    "msg": "value is not a valid integer",
                    "type": "type_error.integer",
                }
            ],
        ),
    ),
)
async def test_article_list_filter_422(
    client: AsyncClient, path: str, expected_errors: List[Dict[str, Any]]
) -> None:
    response = await client.get(path)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.headers["content-type"] == "application/json"
    assert _errors(response.json()) == expected_errors


async def test_feed_filter_422(app: FastAPI, authorized_client: AsyncClient) -> None:
    response = await authorized_client.get(
        app.url_path_for("articles:get-user-feed-articles"),
        params={"limit": 0, "offset": -1},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert _errors(response.json()) == [
        {
            "loc": ["query", "limit"],
            "msg": "ensure this value is greater than or equal to 1",
            "type": "value_error.number.not_ge",
            "ctx": {"limit_value": 1},
        },
        {
            "loc": ["query", "offset"],
            "msg": "ensure this value is greater than or equal to 0",
            "type": "value_error.number.not_ge",
            "ctx": {"limit_value": 0},
        },
    ]


@pytest.mark.parametrize(
    "payload, expected_errors",
    (
        (
            {},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user"],
                    "msg": "field required",
                    "type": "value_error.missing",
                }
            ],
        ),
        (
            {"user": {"email": "a@b.com", "password": "x"}},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user", "username"],
                    "msg": "field required",
                    "type": "value_error.missing",
                }
            ],
        ),
        (
            {"user": {}},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user", "email"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
                {
                    "loc": ["body", "user", "password"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
                {
                    "loc": ["body", "user", "username"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
            ],
        ),
        (
            {"user": {"email": "nope", "password": "x", "username": "u"}},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user", "email"],
                    "msg": "value is not a valid email address",
                    "type": "value_error.email",
                }
            ],
        ),
    ),
)
async def test_registration_422(
    app: FastAPI,
    client: AsyncClient,
    payload: Dict[str, Any],
    expected_errors: List[Dict[str, Any]],
) -> None:
    response = await client.post(app.url_path_for("auth:register"), json=payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert _errors(response.json()) == expected_errors


async def test_login_invalid_email_422(app: FastAPI, client: AsyncClient) -> None:
    response = await client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": "nope", "password": "x"}},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert _errors(response.json()) == [
        {
            "loc": ["body", "user", "email"],
            "msg": "value is not a valid email address",
            "type": "value_error.email",
        }
    ]


async def test_invalid_json_body_422(app: FastAPI, client: AsyncClient) -> None:
    response = await client.post(app.url_path_for("auth:register"), content=b"{bad")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert _errors(response.json()) == [
        {
            "loc": ["body", 1],
            "msg": "Expecting property name enclosed in double quotes: "
            "line 1 column 2 (char 1)",
            "type": "value_error.jsondecode",
            "ctx": {
                "msg": "Expecting property name enclosed in double quotes",
                "doc": "{bad",
                "pos": 1,
                "lineno": 1,
                "colno": 2,
            },
        }
    ]


@pytest.mark.parametrize(
    "user_update, expected_errors",
    (
        (
            {"image": "not a url"},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user", "image"],
                    "msg": "invalid or missing URL scheme",
                    "type": "value_error.url.scheme",
                }
            ],
        ),
        (
            {"image": "https://"},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user", "image"],
                    "msg": "URL host invalid",
                    "type": "value_error.url.host",
                }
            ],
        ),
        (
            {"image": "https://example.com/" + "a" * 2100},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user", "image"],
                    "msg": "ensure this value has at most 2083 characters",
                    "type": "value_error.any_str.max_length",
                    "ctx": {"limit_value": 2083},
                }
            ],
        ),
        (
            {"email": "nope"},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            [
                {
                    "loc": ["body", "user", "email"],
                    "msg": "value is not a valid email address",
                    "type": "value_error.email",
                }
            ],
        ),
    ),
)
async def test_user_update_422(
    app: FastAPI,
    authorized_client: AsyncClient,
    user_update: Dict[str, Any],
    expected_errors: List[Dict[str, Any]],
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"), json={"user": user_update}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert _errors(response.json()) == expected_errors


async def test_user_update_disallowed_url_scheme_is_500(
    app: FastAPI, non_raising_client: AsyncClient, token: str, authorization_prefix: str
) -> None:
    # Current behaviour that looks like a bug: pydantic puts a set in
    # ctx.allowed_schemes, the 422 handler can't JSON-encode it, and the
    # client gets a 500 instead of a 422.
    response = await non_raising_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {"image": "ftp://example.com"}},
        headers={"Authorization": f"{authorization_prefix} {token}"},
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


async def test_create_article_missing_fields_422(
    app: FastAPI, authorized_client: AsyncClient
) -> None:
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"),
        json={"article": {"title": "only title"}},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert _errors(response.json()) == [
        {
            "loc": ["body", "article", "description"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "article", "body"],
            "msg": "field required",
            "type": "value_error.missing",
        },
    ]


async def test_create_comment_missing_body_422(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    response = await authorized_client.post(
        app.url_path_for("comments:create-comment-for-article", slug="test-slug"),
        json={"comment": {}},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert _errors(response.json()) == [
        {
            "loc": ["body", "comment", "body"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]


async def test_comment_id_below_one_422_is_reported_twice(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    # Current behaviour that looks like a bug: comment_id is declared by two
    # dependencies, so the same error is listed twice.
    response = await authorized_client.delete(
        app.url_path_for(
            "comments:delete-comment-from-article", slug="test-slug", comment_id="0"
        )
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    expected_error = {
        "loc": ["path", "comment_id"],
        "msg": "ensure this value is greater than or equal to 1",
        "type": "value_error.number.not_ge",
        "ctx": {"limit_value": 1},
    }
    assert _errors(response.json()) == [expected_error, expected_error]


# --- Authentication header handling ----------------------------------------


def _expired_token() -> str:
    return jwt.create_jwt_token(
        jwt_content={"username": "username"},
        secret_key=environ["SECRET_KEY"],
        expires_delta=timedelta(minutes=-5),
    )


def _nonexistent_user_token() -> str:
    return jwt.create_access_token_for_user(
        User(username="ghost", email="ghost@test.com"), environ["SECRET_KEY"]
    )


AUTH_FAILURES = (
    pytest.param(lambda token: "", strings.AUTHENTICATION_REQUIRED, id="empty"),
    pytest.param(lambda token: "Token", strings.WRONG_TOKEN_PREFIX, id="no-space"),
    pytest.param(lambda token: token, strings.WRONG_TOKEN_PREFIX, id="bare-token"),
    pytest.param(
        lambda token: f"Bearer {token}", strings.WRONG_TOKEN_PREFIX, id="bearer"
    ),
    pytest.param(
        lambda token: f"token {token}", strings.WRONG_TOKEN_PREFIX, id="lowercase"
    ),
    pytest.param(
        lambda token: f"Token  {token}", strings.WRONG_TOKEN_PREFIX, id="two-spaces"
    ),
    pytest.param(
        lambda token: f"Token {token} extra", strings.WRONG_TOKEN_PREFIX, id="3-parts"
    ),
    pytest.param(
        lambda token: "Token garbage", strings.MALFORMED_PAYLOAD, id="garbage-token"
    ),
    pytest.param(
        lambda token: f"Token {_expired_token()}",
        strings.MALFORMED_PAYLOAD,
        id="expired",
    ),
    pytest.param(
        lambda token: f"Token {make_token({'username': 'username'}, secret='nope')}",
        strings.MALFORMED_PAYLOAD,
        id="wrong-secret",
    ),
    pytest.param(
        lambda token: f"Token {make_token({'other': 'x'})}",
        strings.MALFORMED_PAYLOAD,
        id="no-username-claim",
    ),
    pytest.param(
        lambda token: f"Token {_nonexistent_user_token()}",
        strings.MALFORMED_PAYLOAD,
        id="nonexistent-user",
    ),
)


async def test_missing_authorization_header(app: FastAPI, client: AsyncClient) -> None:
    response = await client.get(app.url_path_for("users:get-current-user"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"errors": [strings.AUTHENTICATION_REQUIRED]}


@pytest.mark.parametrize("header_factory, detail", AUTH_FAILURES)
async def test_required_auth_failures(
    app: FastAPI,
    client: AsyncClient,
    token: str,
    header_factory: Callable[[str], str],
    detail: str,
) -> None:
    response = await client.get(
        app.url_path_for("users:get-current-user"),
        headers={"Authorization": header_factory(token)},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"errors": [detail]}


OPTIONAL_AUTH_ROUTES = (
    pytest.param("/api/articles/test-slug", id="get-article"),
    pytest.param("/api/profiles/username", id="get-profile"),
    pytest.param("/api/articles/test-slug/comments", id="list-comments"),
    pytest.param("/api/articles", id="list-articles"),
)


@pytest.mark.parametrize("path", OPTIONAL_AUTH_ROUTES)
@pytest.mark.parametrize("headers", ({}, {"Authorization": ""}), ids=("none", "empty"))
async def test_optional_auth_without_credentials_is_anonymous(
    client: AsyncClient,
    social_graph: None,
    path: str,
    headers: Dict[str, str],
) -> None:
    # An empty Authorization header is treated exactly like no header.
    response = await client.get(path, headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert '"following":false' in response.text
    assert '"following":true' not in response.text
    assert '"favorited":true' not in response.text


@pytest.mark.parametrize("path", OPTIONAL_AUTH_ROUTES)
async def test_optional_auth_with_valid_credentials_is_personalised(
    client: AsyncClient,
    social_graph: None,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
    path: str,
) -> None:
    response = await client.get(path, headers=auth_headers(other_token))

    assert response.status_code == status.HTTP_200_OK
    assert '"following":true' in response.text
    assert '"following":false' not in response.text


@pytest.mark.parametrize("path", OPTIONAL_AUTH_ROUTES)
@pytest.mark.parametrize(
    "header_factory, detail",
    [param for param in AUTH_FAILURES if param.id != "empty"],
)
async def test_optional_auth_with_invalid_credentials_is_403(
    client: AsyncClient,
    test_article: Article,
    token: str,
    path: str,
    header_factory: Callable[[str], str],
    detail: str,
) -> None:
    response = await client.get(path, headers={"Authorization": header_factory(token)})

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"errors": [detail]}


async def test_anonymous_article_flags(
    app: FastAPI,
    client: AsyncClient,
    test_article: Article,
    other_token: str,
    other_follows_test_user: None,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    await client.post(
        app.url_path_for("articles:mark-article-favorite", slug="test-slug"),
        headers=auth_headers(other_token),
    )

    anonymous = (
        await client.get(app.url_path_for("articles:get-article", slug="test-slug"))
    ).json()["article"]
    authorized = (
        await client.get(
            app.url_path_for("articles:get-article", slug="test-slug"),
            headers=auth_headers(other_token),
        )
    ).json()["article"]

    assert (anonymous["favorited"], anonymous["favoritesCount"]) == (False, 1)
    assert anonymous["author"]["following"] is False
    assert (authorized["favorited"], authorized["favoritesCount"]) == (True, 1)
    assert authorized["author"]["following"] is True
