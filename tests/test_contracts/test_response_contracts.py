"""Golden contracts for response envelopes and serialization.

These pin the exact JSON shape the mobile clients consume today
(pydantic 1.9 / fastapi 0.79). Any diff here is a wire-breaking change.
"""
from datetime import datetime, timezone
from typing import Any, Callable, Dict

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from starlette import status

from app.models.domain.articles import Article
from app.models.domain.users import UserInDB
from tests.test_contracts.conftest import (
    ARTICLE_KEYS,
    COMMENT_KEYS,
    PROFILE_KEYS,
    REALWORLD_DATETIME_RE,
    USER_KEYS,
)

pytestmark = pytest.mark.asyncio

ANONYMOUS_AUTHOR = {
    "username": "username",
    "bio": "",
    "image": None,
    "following": False,
}


def _assert_json(response: Response, status_code: int = status.HTTP_200_OK) -> Any:
    assert response.status_code == status_code
    assert response.headers["content-type"] == "application/json"
    return response.json()


def _assert_realworld_datetime(value: str, expected: datetime) -> None:
    assert REALWORLD_DATETIME_RE.match(value), value
    assert "+00:00" not in value
    parsed = datetime.fromisoformat(value[:-1]).replace(tzinfo=timezone.utc)
    assert parsed == expected.astimezone(timezone.utc)


def _expected_test_article(test_article: Article, **overrides: Any) -> Dict[str, Any]:
    return {
        "id": test_article.id_,
        "slug": "test-slug",
        "title": "Test Slug",
        "description": "Slug for tests",
        "body": "Test " * 100,
        "tagList": ["tests", "testing", "pytest"],
        "author": ANONYMOUS_AUTHOR,
        "favorited": False,
        "favoritesCount": 0,
        **overrides,
    }


def _without_timestamps(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"createdAt", "updatedAt"}
    }


async def test_single_article_envelope(
    app: FastAPI, client: AsyncClient, test_article: Article
) -> None:
    body = _assert_json(
        await client.get(app.url_path_for("articles:get-article", slug="test-slug"))
    )

    assert list(body) == ["article"]
    article = body["article"]
    assert list(article) == ARTICLE_KEYS
    assert list(article["author"]) == PROFILE_KEYS
    assert _without_timestamps(article) == _expected_test_article(test_article)
    _assert_realworld_datetime(article["createdAt"], test_article.created_at)
    _assert_realworld_datetime(article["updatedAt"], test_article.updated_at)


async def test_article_id_is_serialized_as_id_not_id_(
    app: FastAPI, client: AsyncClient, test_article: Article
) -> None:
    body = _assert_json(
        await client.get(app.url_path_for("articles:get-article", slug="test-slug"))
    )

    assert body["article"]["id"] == test_article.id_
    assert isinstance(body["article"]["id"], int)
    assert "id_" not in body["article"]


async def test_snake_case_keys_never_leak_into_article_payload(
    app: FastAPI, client: AsyncClient, test_article: Article
) -> None:
    body = _assert_json(
        await client.get(app.url_path_for("articles:get-article", slug="test-slug"))
    )

    for snake in ("tags", "tag_list", "created_at", "updated_at", "favorites_count"):
        assert snake not in body["article"]


async def test_articles_list_envelope(
    app: FastAPI, client: AsyncClient, test_article: Article
) -> None:
    body = _assert_json(await client.get(app.url_path_for("articles:list-articles")))

    assert list(body) == ["articles", "articlesCount"]
    assert body["articlesCount"] == 1
    assert len(body["articles"]) == 1
    article = body["articles"][0]
    assert list(article) == ARTICLE_KEYS
    assert _without_timestamps(article) == _expected_test_article(test_article)
    _assert_realworld_datetime(article["createdAt"], test_article.created_at)


async def test_empty_articles_list_envelope(app: FastAPI, client: AsyncClient) -> None:
    body = _assert_json(await client.get(app.url_path_for("articles:list-articles")))

    assert body == {"articles": [], "articlesCount": 0}


async def test_feed_envelope(
    app: FastAPI,
    client: AsyncClient,
    test_article: Article,
    other_token: str,
    other_follows_test_user: None,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    body = _assert_json(
        await client.get(
            app.url_path_for("articles:get-user-feed-articles"),
            headers=auth_headers(other_token),
        )
    )

    assert list(body) == ["articles", "articlesCount"]
    assert body["articlesCount"] == 1
    article = body["articles"][0]
    assert list(article) == ARTICLE_KEYS
    assert _without_timestamps(article) == _expected_test_article(
        test_article, author={**ANONYMOUS_AUTHOR, "following": True}
    )
    _assert_realworld_datetime(article["createdAt"], test_article.created_at)


async def test_create_article_envelope(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
) -> None:
    body = _assert_json(
        await authorized_client.post(
            app.url_path_for("articles:create-article"),
            json={
                "article": {
                    "title": "Brand New",
                    "description": "desc",
                    "body": "body",
                    "tagList": ["b", "a"],
                }
            },
        ),
        status.HTTP_201_CREATED,
    )

    assert list(body) == ["article"]
    article = body["article"]
    assert list(article) == ARTICLE_KEYS
    assert isinstance(article["id"], int)
    assert REALWORLD_DATETIME_RE.match(article["createdAt"])
    assert REALWORLD_DATETIME_RE.match(article["updatedAt"])
    assert sorted(article["tagList"]) == ["a", "b"]
    assert {
        key: value
        for key, value in article.items()
        if key not in {"createdAt", "updatedAt", "id", "tagList"}
    } == {
        "slug": "brand-new",
        "title": "Brand New",
        "description": "desc",
        "body": "body",
        "author": ANONYMOUS_AUTHOR,
        "favorited": False,
        "favoritesCount": 0,
    }


async def test_favorite_article_envelope(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    body = _assert_json(
        await authorized_client.post(
            app.url_path_for("articles:mark-article-favorite", slug="test-slug")
        )
    )

    assert list(body) == ["article"]
    assert list(body["article"]) == ARTICLE_KEYS
    assert body["article"]["favorited"] is True
    assert body["article"]["favoritesCount"] == 1


async def test_profile_envelope(
    app: FastAPI, client: AsyncClient, test_user: UserInDB
) -> None:
    body = _assert_json(
        await client.get(app.url_path_for("profiles:get-profile", username="username"))
    )

    assert body == {"profile": ANONYMOUS_AUTHOR}
    assert list(body["profile"]) == PROFILE_KEYS


async def test_follow_profile_envelope(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    body = _assert_json(
        await client.post(
            app.url_path_for("profiles:follow-user", username="username"),
            headers=auth_headers(other_token),
        )
    )

    assert body == {"profile": {**ANONYMOUS_AUTHOR, "following": True}}
    assert list(body["profile"]) == PROFILE_KEYS


async def test_current_user_envelope(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB
) -> None:
    body = _assert_json(
        await authorized_client.get(app.url_path_for("users:get-current-user"))
    )

    assert list(body) == ["user"]
    assert list(body["user"]) == USER_KEYS
    assert {key: value for key, value in body["user"].items() if key != "token"} == {
        "username": "username",
        "email": "test@test.com",
        "bio": "",
        "image": None,
    }
    assert isinstance(body["user"]["token"], str)
    assert body["user"]["token"].count(".") == 2


async def test_registration_envelope(app: FastAPI, client: AsyncClient) -> None:
    body = _assert_json(
        await client.post(
            app.url_path_for("auth:register"),
            json={
                "user": {
                    "email": "new@test.com",
                    "username": "newbie",
                    "password": "password",
                }
            },
        ),
        status.HTTP_201_CREATED,
    )

    assert list(body) == ["user"]
    assert list(body["user"]) == USER_KEYS
    assert body["user"]["username"] == "newbie"
    assert body["user"]["email"] == "new@test.com"
    assert body["user"]["bio"] == ""
    assert body["user"]["image"] is None


async def test_login_envelope(
    app: FastAPI, client: AsyncClient, test_user: UserInDB
) -> None:
    body = _assert_json(
        await client.post(
            app.url_path_for("auth:login"),
            json={"user": {"email": "test@test.com", "password": "password"}},
        )
    )

    assert list(body) == ["user"]
    assert list(body["user"]) == USER_KEYS


async def test_tags_envelope(
    app: FastAPI, client: AsyncClient, test_article: Article
) -> None:
    body = _assert_json(await client.get(app.url_path_for("tags:get-all")))

    assert list(body) == ["tags"]
    assert sorted(body["tags"]) == ["pytest", "testing", "tests"]


async def test_empty_tags_envelope(app: FastAPI, client: AsyncClient) -> None:
    body = _assert_json(await client.get(app.url_path_for("tags:get-all")))

    assert body == {"tags": []}


async def test_comment_envelopes(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    created = _assert_json(
        await authorized_client.post(
            app.url_path_for("comments:create-comment-for-article", slug="test-slug"),
            json={"comment": {"body": "first!"}},
        ),
        status.HTTP_201_CREATED,
    )

    assert list(created) == ["comment"]
    comment = created["comment"]
    assert list(comment) == COMMENT_KEYS
    assert isinstance(comment["id"], int)
    assert comment["body"] == "first!"
    assert comment["author"] == ANONYMOUS_AUTHOR
    assert REALWORLD_DATETIME_RE.match(comment["createdAt"])
    assert REALWORLD_DATETIME_RE.match(comment["updatedAt"])

    listed = _assert_json(
        await authorized_client.get(
            app.url_path_for("comments:get-comments-for-article", slug="test-slug")
        )
    )

    assert listed == {"comments": [comment]}


async def test_empty_comments_envelope(
    app: FastAPI, client: AsyncClient, test_article: Article
) -> None:
    body = _assert_json(
        await client.get(
            app.url_path_for("comments:get-comments-for-article", slug="test-slug")
        )
    )

    assert body == {"comments": []}


async def test_delete_endpoints_return_empty_204(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    comment = (
        await authorized_client.post(
            app.url_path_for("comments:create-comment-for-article", slug="test-slug"),
            json={"comment": {"body": "bye"}},
        )
    ).json()["comment"]

    comment_response = await authorized_client.delete(
        app.url_path_for(
            "comments:delete-comment-from-article",
            slug="test-slug",
            comment_id=str(comment["id"]),
        )
    )
    article_response = await authorized_client.delete(
        app.url_path_for("articles:delete-article", slug="test-slug")
    )

    for response in (comment_response, article_response):
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
