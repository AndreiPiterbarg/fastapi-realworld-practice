from typing import Callable, Dict, List

import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.db.repositories.articles import ArticlesRepository
from app.models.domain.articles import Article
from app.models.domain.users import UserInDB
from app.resources import strings
from app.services.articles import get_slug_for_article

# --- slugs ------------------------------------------------------------------


@pytest.mark.parametrize(
    "title, slug",
    (
        ("Héllo Wörld! 你好 & <b>Ça va?</b>", "hello-world-ni-hao-b-ca-va-b"),
        ("  Leading & trailing  ", "leading-trailing"),
        ("Already-a-slug", "already-a-slug"),
        ("100% Fun", "100-fun"),
        ("Привет мир", "privet-mir"),
        ("emoji 🎉 party", "emoji-party"),
        ("Straße", "strasse"),
        ("a_b c--d", "a-b-c-d"),
        ('It\'s "quoted"', "it-s-quoted"),
        ("!!!", ""),
    ),
)
def test_get_slug_for_article(title: str, slug: str) -> None:
    assert get_slug_for_article(title) == slug


async def test_create_article_uses_generated_unicode_slug(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB
) -> None:
    title = "Héllo Wörld! 你好 & <b>Ça va?</b>"
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"),
        json={"article": {"title": title, "description": "d", "body": "b"}},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["article"]["slug"] == "hello-world-ni-hao-b-ca-va-b"
    assert response.json()["article"]["title"] == title


async def test_create_article_with_punctuation_only_title_gets_empty_slug(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB
) -> None:
    # Current behaviour that looks like a bug: the article is created with an
    # empty slug and can't be reached through /articles/{slug}.
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"),
        json={"article": {"title": "!!!", "description": "d", "body": "b"}},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["article"]["slug"] == ""


async def test_create_article_with_colliding_slug_is_400(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"),
        json={"article": {"title": "TEST slug!", "description": "d", "body": "b"}},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"errors": [strings.ARTICLE_ALREADY_EXISTS]}


async def test_updating_title_regenerates_slug(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    response = await authorized_client.put(
        app.url_path_for("articles:update-article", slug="test-slug"),
        json={"article": {"title": "Brand New Title"}},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["article"]["slug"] == "brand-new-title"
    assert response.json()["article"]["title"] == "Brand New Title"

    old = await authorized_client.get(
        app.url_path_for("articles:get-article", slug="test-slug")
    )
    new = await authorized_client.get(
        app.url_path_for("articles:get-article", slug="brand-new-title")
    )
    assert old.status_code == status.HTTP_404_NOT_FOUND
    assert new.status_code == status.HTTP_200_OK


async def test_updating_title_to_existing_slug_is_500(
    app: FastAPI,
    non_raising_client: AsyncClient,
    test_article: Article,
    test_user: UserInDB,
    pool: Pool,
    token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    # Current behaviour that looks like a bug: unlike create, update does not
    # check slug collisions, so the DB unique constraint surfaces as a 500.
    async with pool.acquire() as connection:
        await ArticlesRepository(connection).create_article(
            slug="second", title="Second", description="d", body="b", author=test_user
        )

    response = await non_raising_client.put(
        app.url_path_for("articles:update-article", slug="second"),
        json={"article": {"title": "Test Slug"}},
        headers=auth_headers(token),
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# --- article partial updates & permissions ----------------------------------


@pytest.mark.parametrize(
    "update, expected",
    (
        ({}, {}),
        ({"body": "new body"}, {"body": "new body"}),
        ({"description": "new desc"}, {"description": "new desc"}),
        # Current behaviour: empty strings are treated as "not provided".
        ({"title": "", "body": "", "description": ""}, {}),
        # Unknown fields (including slug and tagList) are ignored.
        ({"slug": "hijack", "tagList": ["x"]}, {}),
    ),
)
async def test_partial_article_update(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    update: Dict[str, str],
    expected: Dict[str, str],
) -> None:
    response = await authorized_client.put(
        app.url_path_for("articles:update-article", slug="test-slug"),
        json={"article": update},
    )

    assert response.status_code == status.HTTP_200_OK
    article = response.json()["article"]
    unchanged = {
        "slug": "test-slug",
        "title": "Test Slug",
        "description": "Slug for tests",
        "body": "Test " * 100,
        "tagList": ["tests", "testing", "pytest"],
    }
    assert {key: article[key] for key in unchanged} == {**unchanged, **expected}


@pytest.mark.parametrize(
    "method, route_name, json",
    (
        ("PUT", "articles:update-article", {"article": {"title": "x"}}),
        ("DELETE", "articles:delete-article", None),
    ),
)
async def test_non_author_cannot_modify_article(
    app: FastAPI,
    client: AsyncClient,
    test_article: Article,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
    method: str,
    route_name: str,
    json: Dict[str, Dict[str, str]],
) -> None:
    response = await client.request(
        method,
        app.url_path_for(route_name, slug="test-slug"),
        json=json,
        headers=auth_headers(other_token),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"errors": [strings.USER_IS_NOT_AUTHOR_OF_ARTICLE]}


@pytest.mark.parametrize(
    "method, route_name, json",
    (
        ("GET", "articles:get-article", None),
        ("PUT", "articles:update-article", {"article": {"title": "x"}}),
        ("DELETE", "articles:delete-article", None),
        ("POST", "articles:mark-article-favorite", None),
        ("DELETE", "articles:unmark-article-favorite", None),
        ("GET", "comments:get-comments-for-article", None),
        ("POST", "comments:create-comment-for-article", {"comment": {"body": "x"}}),
    ),
)
async def test_nonexistent_slug_is_404(
    app: FastAPI,
    authorized_client: AsyncClient,
    method: str,
    route_name: str,
    json: Dict[str, Dict[str, str]],
) -> None:
    response = await authorized_client.request(
        method, app.url_path_for(route_name, slug="missing"), json=json
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"errors": [strings.ARTICLE_DOES_NOT_EXIST_ERROR]}


async def test_non_author_cannot_delete_comment(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    comment = (
        await authorized_client.post(
            app.url_path_for("comments:create-comment-for-article", slug="test-slug"),
            json={"comment": {"body": "mine"}},
        )
    ).json()["comment"]

    response = await authorized_client.delete(
        app.url_path_for(
            "comments:delete-comment-from-article",
            slug="test-slug",
            comment_id=str(comment["id"]),
        ),
        headers=auth_headers(other_token),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"errors": [strings.USER_IS_NOT_AUTHOR_OF_ARTICLE]}


async def test_nonexistent_comment_is_404(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    response = await authorized_client.delete(
        app.url_path_for(
            "comments:delete-comment-from-article",
            slug="test-slug",
            comment_id="999999",
        )
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"errors": [strings.COMMENT_DOES_NOT_EXIST]}


# --- article list filters & pagination --------------------------------------


@pytest.fixture
async def catalogue(test_user: UserInDB, other_user: UserInDB, pool: Pool) -> None:
    async with pool.acquire() as connection:
        repo = ArticlesRepository(connection)
        mine_a = await repo.create_article(
            slug="mine-a",
            title="a",
            description="d",
            body="b",
            author=test_user,
            tags=["red", "blue"],
        )
        await repo.create_article(
            slug="mine-b",
            title="b",
            description="d",
            body="b",
            author=test_user,
            tags=["red"],
        )
        await repo.create_article(
            slug="mine-c",
            title="c",
            description="d",
            body="b",
            author=test_user,
        )
        theirs_a = await repo.create_article(
            slug="theirs-a",
            title="d",
            description="d",
            body="b",
            author=other_user,
            tags=["red"],
        )
        await repo.create_article(
            slug="theirs-b",
            title="e",
            description="d",
            body="b",
            author=other_user,
            tags=["blue"],
        )
        await repo.add_article_into_favorites(article=mine_a, user=other_user)
        await repo.add_article_into_favorites(article=theirs_a, user=other_user)
        await repo.add_article_into_favorites(article=theirs_a, user=test_user)


def _slugs(body: Dict[str, List[Dict[str, str]]]) -> List[str]:
    return sorted(article["slug"] for article in body["articles"])


@pytest.mark.parametrize(
    "params, expected",
    (
        ({}, ["mine-a", "mine-b", "mine-c", "theirs-a", "theirs-b"]),
        ({"tag": "red"}, ["mine-a", "mine-b", "theirs-a"]),
        ({"tag": "blue"}, ["mine-a", "theirs-b"]),
        ({"tag": "missing"}, []),
        ({"author": "username"}, ["mine-a", "mine-b", "mine-c"]),
        ({"author": "other"}, ["theirs-a", "theirs-b"]),
        ({"author": "nobody"}, []),
        ({"favorited": "other"}, ["mine-a", "theirs-a"]),
        ({"favorited": "username"}, ["theirs-a"]),
        ({"tag": "red", "author": "username"}, ["mine-a", "mine-b"]),
        ({"tag": "red", "favorited": "other"}, ["mine-a", "theirs-a"]),
        ({"author": "other", "favorited": "username"}, ["theirs-a"]),
        ({"tag": "blue", "author": "other", "favorited": "other"}, []),
        ({"tag": "red", "author": "username", "favorited": "other"}, ["mine-a"]),
        # Empty values are treated as "no filter".
        (
            {"tag": "", "author": "", "favorited": ""},
            ["mine-a", "mine-b", "mine-c", "theirs-a", "theirs-b"],
        ),
    ),
)
async def test_article_filters(
    app: FastAPI,
    client: AsyncClient,
    catalogue: None,
    params: Dict[str, str],
    expected: List[str],
) -> None:
    response = await client.get(
        app.url_path_for("articles:list-articles"), params=params
    )

    assert response.status_code == status.HTTP_200_OK
    assert _slugs(response.json()) == expected
    assert response.json()["articlesCount"] == len(expected)


@pytest.mark.parametrize(
    "limit, offset, size",
    ((1, 0, 1), (2, 0, 2), (2, 2, 2), (2, 4, 1), (2, 5, 0), (20, 0, 5), (5, 10, 0)),
)
async def test_articles_count_is_page_size_not_total(
    app: FastAPI,
    client: AsyncClient,
    catalogue: None,
    limit: int,
    offset: int,
    size: int,
) -> None:
    # Current behaviour that differs from the RealWorld spec: articlesCount is
    # len(page), not the total number of matching articles.
    response = await client.get(
        app.url_path_for("articles:list-articles"),
        params={"limit": limit, "offset": offset},
    )

    body = response.json()
    assert len(body["articles"]) == size
    assert body["articlesCount"] == size


async def test_pagination_pages_are_disjoint_and_complete(
    app: FastAPI, client: AsyncClient, catalogue: None
) -> None:
    # The list query has no ORDER BY, so only page membership is pinned.
    pages = [
        _slugs(
            (
                await client.get(
                    app.url_path_for("articles:list-articles"),
                    params={"limit": 2, "offset": offset},
                )
            ).json()
        )
        for offset in (0, 2, 4)
    ]

    flattened = [slug for page in pages for slug in page]
    assert [len(page) for page in pages] == [2, 2, 1]
    assert sorted(flattened) == ["mine-a", "mine-b", "mine-c", "theirs-a", "theirs-b"]


async def test_filtered_pagination(
    app: FastAPI, client: AsyncClient, catalogue: None
) -> None:
    response = await client.get(
        app.url_path_for("articles:list-articles"),
        params={"tag": "red", "limit": 2, "offset": 2},
    )

    body = response.json()
    assert body["articlesCount"] == 1
    assert len(body["articles"]) == 1


async def test_list_flags_for_viewer(
    app: FastAPI,
    client: AsyncClient,
    catalogue: None,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    anonymous = (await client.get(app.url_path_for("articles:list-articles"))).json()[
        "articles"
    ]
    as_other = (
        await client.get(
            app.url_path_for("articles:list-articles"),
            headers=auth_headers(other_token),
        )
    ).json()["articles"]

    def flags(articles: List[Dict]) -> Dict[str, tuple]:
        return {
            article["slug"]: (article["favorited"], article["favoritesCount"])
            for article in articles
        }

    assert flags(anonymous) == {
        "mine-a": (False, 1),
        "mine-b": (False, 0),
        "mine-c": (False, 0),
        "theirs-a": (False, 2),
        "theirs-b": (False, 0),
    }
    assert flags(as_other) == {
        "mine-a": (True, 1),
        "mine-b": (False, 0),
        "mine-c": (False, 0),
        "theirs-a": (True, 2),
        "theirs-b": (False, 0),
    }


async def test_feed_pagination_and_count(
    app: FastAPI,
    client: AsyncClient,
    catalogue: None,
    other_token: str,
    other_follows_test_user: None,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    full = (
        await client.get(
            app.url_path_for("articles:get-user-feed-articles"),
            headers=auth_headers(other_token),
        )
    ).json()
    page = (
        await client.get(
            app.url_path_for("articles:get-user-feed-articles"),
            params={"limit": 2, "offset": 1},
            headers=auth_headers(other_token),
        )
    ).json()

    assert _slugs(full) == ["mine-a", "mine-b", "mine-c"]
    assert full["articlesCount"] == 3
    assert len(page["articles"]) == 2
    assert page["articlesCount"] == 2


async def test_feed_is_empty_when_following_nobody(
    app: FastAPI, authorized_client: AsyncClient, catalogue: None
) -> None:
    response = await authorized_client.get(
        app.url_path_for("articles:get-user-feed-articles")
    )

    assert response.json() == {"articles": [], "articlesCount": 0}


# --- favorites ---------------------------------------------------------------


async def test_favorite_is_not_idempotent(
    app: FastAPI,
    client: AsyncClient,
    test_article: Article,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    url = app.url_path_for("articles:mark-article-favorite", slug="test-slug")
    headers = auth_headers(other_token)

    first = await client.post(url, headers=headers)
    second = await client.post(url, headers=headers)
    viewed = await client.get(
        app.url_path_for("articles:get-article", slug="test-slug"), headers=headers
    )

    assert first.status_code == status.HTTP_200_OK
    assert (
        first.json()["article"]["favorited"],
        first.json()["article"]["favoritesCount"],
    ) == (True, 1)
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert second.json() == {"errors": [strings.ARTICLE_IS_ALREADY_FAVORITED]}
    assert (
        viewed.json()["article"]["favorited"],
        viewed.json()["article"]["favoritesCount"],
    ) == (True, 1)


async def test_unfavorite_is_not_idempotent(
    app: FastAPI,
    client: AsyncClient,
    test_article: Article,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    headers = auth_headers(other_token)
    await client.post(
        app.url_path_for("articles:mark-article-favorite", slug="test-slug"),
        headers=headers,
    )
    url = app.url_path_for("articles:unmark-article-favorite", slug="test-slug")

    first = await client.delete(url, headers=headers)
    second = await client.delete(url, headers=headers)

    assert first.status_code == status.HTTP_200_OK
    assert (
        first.json()["article"]["favorited"],
        first.json()["article"]["favoritesCount"],
    ) == (False, 0)
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert second.json() == {"errors": [strings.ARTICLE_IS_NOT_FAVORITED]}


async def test_author_can_favorite_own_article(
    app: FastAPI, authorized_client: AsyncClient, test_article: Article
) -> None:
    response = await authorized_client.post(
        app.url_path_for("articles:mark-article-favorite", slug="test-slug")
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["article"]["favorited"] is True


@pytest.mark.parametrize("method", ("POST", "DELETE"))
async def test_favorite_requires_auth(
    app: FastAPI, client: AsyncClient, test_article: Article, method: str
) -> None:
    response = await client.request(
        method, app.url_path_for("articles:mark-article-favorite", slug="test-slug")
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"errors": [strings.AUTHENTICATION_REQUIRED]}


# --- follow / unfollow ------------------------------------------------------


async def test_following_flag_for_anonymous_and_follower(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    other_token: str,
    token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    url = app.url_path_for("profiles:get-profile", username="username")

    follow = await client.post(
        app.url_path_for("profiles:follow-user", username="username"),
        headers=auth_headers(other_token),
    )
    anonymous = await client.get(url)
    follower = await client.get(url, headers=auth_headers(other_token))
    own = await client.get(url, headers=auth_headers(token))

    assert follow.json()["profile"]["following"] is True
    assert anonymous.json()["profile"]["following"] is False
    assert follower.json()["profile"]["following"] is True
    assert own.json()["profile"]["following"] is False


async def test_follow_and_unfollow_are_not_idempotent(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    other_token: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> None:
    url = app.url_path_for("profiles:follow-user", username="username")
    headers = auth_headers(other_token)

    responses = [
        await client.post(url, headers=headers),
        await client.post(url, headers=headers),
        await client.delete(url, headers=headers),
        await client.delete(url, headers=headers),
    ]

    assert [response.status_code for response in responses] == [200, 400, 200, 400]
    assert responses[0].json()["profile"]["following"] is True
    assert responses[1].json() == {"errors": [strings.USER_IS_ALREADY_FOLLOWED]}
    assert responses[2].json()["profile"]["following"] is False
    assert responses[3].json() == {"errors": [strings.USER_IS_NOT_FOLLOWED]}


@pytest.mark.parametrize(
    "method, detail",
    (
        ("POST", strings.UNABLE_TO_FOLLOW_YOURSELF),
        ("DELETE", strings.UNABLE_TO_UNSUBSCRIBE_FROM_YOURSELF),
    ),
)
async def test_cannot_follow_or_unfollow_self(
    app: FastAPI, authorized_client: AsyncClient, method: str, detail: str
) -> None:
    response = await authorized_client.request(
        method, app.url_path_for("profiles:follow-user", username="username")
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"errors": [detail]}


@pytest.mark.parametrize("method", ("POST", "DELETE"))
async def test_follow_nonexistent_user_is_404(
    app: FastAPI, authorized_client: AsyncClient, method: str
) -> None:
    response = await authorized_client.request(
        method, app.url_path_for("profiles:follow-user", username="nobody")
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"errors": [strings.USER_DOES_NOT_EXIST_ERROR]}


# --- user updates -----------------------------------------------------------


@pytest.mark.parametrize(
    "update, expected",
    (
        ({}, {}),
        ({"bio": "new bio"}, {"bio": "new bio"}),
        ({"image": "https://example.com"}, {"image": "https://example.com"}),
        ({"username": "renamed"}, {"username": "renamed"}),
        ({"email": "renamed@test.com"}, {"email": "renamed@test.com"}),
        # Re-submitting your own username/email is allowed.
        ({"username": "username", "email": "test@test.com"}, {}),
        # Current behaviour: empty strings are treated as "not provided".
        ({"bio": "", "username": "", "password": ""}, {}),
        ({"bio": None, "image": None}, {}),
    ),
)
async def test_partial_user_update(
    app: FastAPI,
    authorized_client: AsyncClient,
    test_user: UserInDB,
    update: Dict[str, str],
    expected: Dict[str, str],
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"), json={"user": update}
    )

    assert response.status_code == status.HTTP_200_OK
    user = response.json()["user"]
    unchanged = {
        "username": "username",
        "email": "test@test.com",
        "bio": "",
        "image": None,
    }
    assert {key: user[key] for key in unchanged} == {**unchanged, **expected}


async def test_password_update_changes_login(
    app: FastAPI,
    authorized_client: AsyncClient,
    client: AsyncClient,
    test_user: UserInDB,
) -> None:
    await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {"password": "new-password"}},
    )

    old = await client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": "test@test.com", "password": "password"}},
    )
    new = await client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": "test@test.com", "password": "new-password"}},
    )

    assert old.status_code == status.HTTP_400_BAD_REQUEST
    assert new.status_code == status.HTTP_200_OK


@pytest.mark.parametrize(
    "update, detail",
    (
        ({"username": "other"}, strings.USERNAME_TAKEN),
        ({"email": "other@test.com"}, strings.EMAIL_TAKEN),
        ({"username": "other", "email": "other@test.com"}, strings.USERNAME_TAKEN),
    ),
)
async def test_user_update_to_taken_credentials_is_400(
    app: FastAPI,
    authorized_client: AsyncClient,
    other_user: UserInDB,
    update: Dict[str, str],
    detail: str,
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"), json={"user": update}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"errors": [detail]}


async def test_token_of_renamed_user_stops_working(
    app: FastAPI, authorized_client: AsyncClient, test_user: UserInDB
) -> None:
    response = await authorized_client.put(
        app.url_path_for("users:update-current-user"),
        json={"user": {"username": "renamed"}},
    )
    stale = await authorized_client.get(app.url_path_for("users:get-current-user"))

    assert response.status_code == status.HTTP_200_OK
    assert stale.status_code == status.HTTP_403_FORBIDDEN
    assert stale.json() == {"errors": [strings.MALFORMED_PAYLOAD]}


# --- registration / login ---------------------------------------------------


@pytest.mark.parametrize(
    "user, detail",
    (
        ({"username": "username", "email": "fresh@test.com"}, strings.USERNAME_TAKEN),
        ({"username": "fresh", "email": "test@test.com"}, strings.EMAIL_TAKEN),
        # Username is checked first.
        ({"username": "username", "email": "test@test.com"}, strings.USERNAME_TAKEN),
    ),
)
async def test_duplicate_registration_is_400(
    app: FastAPI,
    client: AsyncClient,
    test_user: UserInDB,
    user: Dict[str, str],
    detail: str,
) -> None:
    # The RealWorld spec says 422, but the app returns 400.
    response = await client.post(
        app.url_path_for("auth:register"),
        json={"user": {**user, "password": "password"}},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"errors": [detail]}


@pytest.mark.parametrize(
    "credentials",
    (
        {"email": "test@test.com", "password": "wrong"},
        {"email": "nobody@test.com", "password": "password"},
        {"email": "TEST@test.com", "password": "password"},
    ),
)
async def test_failed_login_is_400(
    app: FastAPI, client: AsyncClient, test_user: UserInDB, credentials: Dict[str, str]
) -> None:
    # Unknown email and wrong password are indistinguishable; email match is
    # case-sensitive on the local part.
    response = await client.post(
        app.url_path_for("auth:login"), json={"user": credentials}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"errors": [strings.INCORRECT_LOGIN_INPUT]}


async def test_login_email_domain_is_case_insensitive(
    app: FastAPI, client: AsyncClient, test_user: UserInDB
) -> None:
    # EmailStr lowercases the domain before lookup.
    response = await client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": "test@TEST.COM", "password": "password"}},
    )

    assert response.status_code == status.HTTP_200_OK
