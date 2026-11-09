"""Golden contracts for embedded bodies that are not JSON objects.

Expected values were recorded from old main (pydantic 1.9.2). This file
passes unchanged there.
"""
from typing import Any, Dict, List, Tuple

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.models.domain.articles import Article
from app.models.domain.users import UserInDB

pytestmark = pytest.mark.asyncio

NON_OBJECTS: Tuple[Any, ...] = (
    "abc",
    "",
    5,
    1.5,
    True,
    [],
    ["ab"],
    [["email", "a@b.com"]],
    [{"a": 1}],
)
NOT_A_DICT: Tuple[Any, ...] = ("abc", 5, 1.5, True, [["a"]], [{"bio": "x"}])
EMPTY_UPDATES: Tuple[Any, ...] = ("", [], ["ab"], [["title", "t"]])


def _missing(*loc: str) -> Dict[str, Any]:
    return {"loc": list(loc), "msg": "field required", "type": "value_error.missing"}


def _str_expected(*loc: str) -> Dict[str, Any]:
    return {"loc": list(loc), "msg": "str type expected", "type": "type_error.str"}


def _errors(response: Any) -> List[Dict[str, Any]]:
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    return response.json()["errors"]


@pytest.mark.parametrize("value", NON_OBJECTS)
async def test_register_with_non_object_user(  # pydantic-v1 contract
    app: FastAPI,
    client: AsyncClient,
    value: Any,
) -> None:
    response = await client.post(
        app.url_path_for("auth:register"), json={"user": value}
    )

    assert _errors(response) == [
        _missing("body", "user", "email"),
        _missing("body", "user", "password"),
        _missing("body", "user", "username"),
    ]


@pytest.mark.parametrize("value", NON_OBJECTS)
async def test_login_with_non_object_user(  # pydantic-v1 contract
    app: FastAPI,
    client: AsyncClient,
    value: Any,
) -> None:
    response = await client.post(app.url_path_for("auth:login"), json={"user": value})

    assert _errors(response) == [
        _missing("body", "user", "email"),
        _missing("body", "user", "password"),
    ]


@pytest.mark.parametrize("route_name", ("auth:register", "auth:login"))
async def test_null_user_is_missing(  # pydantic-v1 contract
    app: FastAPI,
    client: AsyncClient,
    route_name: str,
) -> None:
    response = await client.post(app.url_path_for(route_name), json={"user": None})

    assert _errors(response) == [_missing("body", "user")]


@pytest.mark.parametrize("value", NOT_A_DICT)
async def test_update_user_with_non_dict_user(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    value: Any,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": value},
    )

    assert _errors(response) == [
        {
            "loc": ["body", "user"],
            "msg": "value is not a valid dict",
            "type": "type_error.dict",
        },
    ]


async def test_update_user_with_non_str_keys(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": [[1, 2]]},
    )

    assert _errors(response) == [
        {
            "loc": ["body", "user"],
            "msg": "keywords must be strings",
            "type": "type_error",
        },
    ]


@pytest.mark.parametrize("value", EMPTY_UPDATES)
async def test_update_user_with_empty_sequence_is_empty_update(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    value: Any,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": value},
    )

    assert response.status_code == status.HTTP_200_OK
    user = response.json()["user"]
    assert (user["username"], user["email"], user["bio"], user["image"]) == (
        test_user.username,
        test_user.email,
        "",
        None,
    )


async def test_update_user_with_list_of_pairs(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": [["bio", "x"]]},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user"]["bio"] == "x"


async def test_update_user_with_list_of_pairs_validates_values(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": [["bio", "x"], ["email", "nope"]]},
    )

    assert _errors(response) == [
        {
            "loc": ["body", "user", "email"],
            "msg": "value is not a valid email address",
            "type": "value_error.email",
        },
    ]


@pytest.mark.parametrize(
    "value, title_error",
    (
        ("abc", _str_expected),
        ("", _str_expected),
        (5, _missing),
        (True, _missing),
        ([], _missing),
        ([["title", "t"]], _missing),
    ),
)
async def test_create_article_with_non_object_article(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    value: Any,
    title_error: Any,
) -> None:
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"),
        json={"article": value},
    )

    # str has a ``title`` method, which pydantic 1.9 read as the title field.
    assert _errors(response) == [
        title_error("body", "article", "title"),
        _missing("body", "article", "description"),
        _missing("body", "article", "body"),
    ]


@pytest.mark.parametrize("value", ("abc", ""))
async def test_update_article_with_str_article(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    value: str,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("articles:update-article", slug=test_article.slug),
        json={"article": value},
    )

    assert _errors(response) == [_str_expected("body", "article", "title")]


@pytest.mark.parametrize("value", (5, True, [], [["title", "t"]]))
async def test_update_article_with_non_object_is_empty_update(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    value: Any,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("articles:update-article", slug=test_article.slug),
        json={"article": value},
    )

    assert response.status_code == status.HTTP_200_OK
    article = response.json()["article"]
    assert (article["slug"], article["title"], article["body"]) == (
        test_article.slug,
        test_article.title,
        test_article.body,
    )


@pytest.mark.parametrize("value", NON_OBJECTS)
async def test_create_comment_with_non_object_comment(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    value: Any,
) -> None:
    response = await authorized_client.post(
        app.url_path_for(
            "comments:create-comment-for-article",
            slug=test_article.slug,
        ),
        json={"comment": value},
    )

    assert _errors(response) == [_missing("body", "comment", "body")]
