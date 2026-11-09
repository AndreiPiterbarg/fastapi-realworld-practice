"""Golden contracts for pydantic 1.9's EmailStr and str coercion, rebuilt for v2.

Every expected value below was recorded by sending the same request to the
pre-upgrade API (pydantic 1.9.2, email-validator 1.1.3).
"""
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.models.domain.articles import Article

pytestmark = pytest.mark.asyncio


def _errors(body: Any) -> List[Any]:
    assert list(body) == ["errors"]
    assert isinstance(body["errors"], list)
    return body["errors"]


def _error(loc: List[Any], msg: str, error_type: str) -> Dict[str, Any]:
    return {"loc": loc, "msg": msg, "type": error_type}


def _email_error(*loc: Any) -> Dict[str, Any]:
    return _error(
        ["body", "user", *loc],
        "value is not a valid email address",
        "value_error.email",
    )


NONE_MSG = "none is not an allowed value"
NONE_TYPE = "type_error.none.not_allowed"
STR_MSG = "str type expected"
STR_TYPE = "type_error.str"


@pytest.mark.parametrize(
    "sent_email, stored_email",
    (
        # pydantic-v1 contract: special-use domains are accepted
        ("a@example.test", "a@example.test"),
        ("a@foo.local", "a@foo.local"),
        ("a@foo.localhost", "a@foo.localhost"),
        ("a@foo.onion", "a@foo.onion"),
        ("a@foo.invalid", "a@foo.invalid"),
        ("a@1.in-addr.arpa", "a@1.in-addr.arpa"),
        # pydantic-v1 contract: the domain is lowercased but not IDNA-converted
        ("a@xn--mnchen-3ya.de", "a@xn--mnchen-3ya.de"),
        ("a@M\u00fcnchen.DE", "a@m\u00fcnchen.de"),
        # pydantic-v1 contract, looks like a bug: the "fi" ligature is kept
        ("a@\ufb01.com", "a@\ufb01.com"),
        # pydantic-v1 contract: the local part keeps its case
        ("Joe.Bloggs@Example.COM", "Joe.Bloggs@example.com"),
        # pydantic-v1 contract: "Name <address>" and surrounding spaces are removed
        ("John Doe <a@b.com>", "a@b.com"),
        ("  a@b.com  ", "a@b.com"),
        # pydantic-v1 contract, looks like a bug: a zero-width space in the
        # local part is accepted and stored
        ("a\u200b@b.com", "a\u200b@b.com"),
    ),
)
async def test_registered_email_is_stored_as_v1_and_can_log_in(
    app: FastAPI, client: AsyncClient, sent_email: str, stored_email: str
) -> None:
    response = await client.post(
        app.url_path_for("auth:register"),
        json={"user": {"email": sent_email, "username": "u", "password": "p"}},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["user"]["email"] == stored_email

    for login_email in (sent_email, stored_email):
        response = await client.post(
            app.url_path_for("auth:login"),
            json={"user": {"email": login_email, "password": "p"}},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["user"]["email"] == stored_email


@pytest.mark.parametrize(
    "sent_email, stored_email",
    (
        ("a@example.test", "a@example.test"),
        ("a@xn--mnchen-3ya.de", "a@xn--mnchen-3ya.de"),
        ("A@M\u00fcnchen.DE", "A@m\u00fcnchen.de"),
    ),
)
async def test_user_update_stores_email_as_v1(
    app: FastAPI, authorized_client: AsyncClient, sent_email: str, stored_email: str
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {"email": sent_email}},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user"]["email"] == stored_email

    response = await authorized_client.get(app.url_path_for("users:get-current-user"))
    assert response.json()["user"]["email"] == stored_email


@pytest.mark.parametrize(
    "email, expected_error",
    (
        # pydantic-v1 contract
        # pydantic-v1 contract, looks like a bug: a quoted display name is
        # rejected although "John Doe <a@b.com>" is accepted
        ('"John" <a@b.com>', _email_error("email")),
        ('"a"@b.com', _email_error("email")),
        ("a@b", _email_error("email")),
        ("a@b.1", _email_error("email")),
        ("a@b..com", _email_error("email")),
        ("a@-b.com", _email_error("email")),
        ("a@b_c.com", _email_error("email")),
        ("a@@b.com", _email_error("email")),
        ("a@{0}.com".format("b" * 64), _email_error("email")),
        ("{0}@b.com".format("\u00e9" * 65), _email_error("email")),
        ("a@{0}.com".format(".".join(["b" * 63] * 4)), _email_error("email")),
        # pydantic-v1 contract: bools and numbers become strings first
        (True, _email_error("email")),
        (1, _email_error("email")),
        (None, _error(["body", "user", "email"], NONE_MSG, NONE_TYPE)),
        ([], _error(["body", "user", "email"], STR_MSG, STR_TYPE)),
    ),
)
async def test_registration_rejects_email_as_v1(
    app: FastAPI, client: AsyncClient, email: Any, expected_error: Dict[str, Any]
) -> None:
    response = await client.post(
        app.url_path_for("auth:register"),
        json={"user": {"email": email, "username": "u", "password": "p"}},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert _errors(response.json()) == [expected_error]


async def test_bools_and_numbers_in_registration_become_strings(
    app: FastAPI, client: AsyncClient
) -> None:
    response = await client.post(
        app.url_path_for("auth:register"),
        json={"user": {"email": "a@b.com", "username": True, "password": False}},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["user"]["username"] == "True"

    response = await client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": "a@b.com", "password": "False"}},
    )
    assert response.status_code == status.HTTP_200_OK


async def test_bools_in_user_update_become_strings(
    app: FastAPI, authorized_client: AsyncClient
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {"username": False, "bio": True, "password": 1.5}},
    )
    assert response.status_code == status.HTTP_200_OK
    user = response.json()["user"]
    assert (user["username"], user["bio"]) == ("False", "True")

    response = await authorized_client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": "test@test.com", "password": "1.5"}},
    )
    assert response.status_code == status.HTTP_200_OK


async def test_bools_and_numbers_in_new_article_become_strings(
    app: FastAPI, authorized_client: AsyncClient
) -> None:
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"),
        json={
            "article": {
                "title": True,
                "description": False,
                "body": 1.5,
                "tagList": [True, 2, "x"],
            }
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    article = response.json()["article"]
    assert article["slug"] == "true"
    assert (article["title"], article["description"], article["body"]) == (
        "True",
        "False",
        "1.5",
    )
    assert sorted(article["tagList"]) == ["2", "True", "x"]


async def test_bools_in_article_update_and_comment_become_strings(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    response = await authorized_client.post(
        app.url_path_for("comments:create-comment-for-article", slug=test_article.slug),
        json={"comment": {"body": False}},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["comment"]["body"] == "False"

    response = await authorized_client.put(
        app.url_path_for("articles:update-article", slug=test_article.slug),
        json={"article": {"title": True, "body": False}},
    )
    assert response.status_code == status.HTTP_200_OK
    article = response.json()["article"]
    assert (article["slug"], article["title"], article["body"]) == (
        "true",
        "True",
        "False",
    )


@pytest.mark.parametrize(
    "article, expected_errors",
    (
        # pydantic-v1 contract
        (
            {"title": None, "description": [], "body": {}, "tagList": ["a", None, []]},
            [
                _error(["body", "article", "title"], NONE_MSG, NONE_TYPE),
                _error(["body", "article", "description"], STR_MSG, STR_TYPE),
                _error(["body", "article", "body"], STR_MSG, STR_TYPE),
                _error(["body", "article", "tagList", 1], NONE_MSG, NONE_TYPE),
                _error(["body", "article", "tagList", 2], STR_MSG, STR_TYPE),
            ],
        ),
    ),
)
async def test_non_scalar_article_fields_are_rejected_as_v1(
    app: FastAPI,
    authorized_client: AsyncClient,
    article: Dict[str, Any],
    expected_errors: List[Dict[str, Any]],
) -> None:
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"), json={"article": article}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert _errors(response.json()) == expected_errors
