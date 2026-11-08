import re
from datetime import timedelta
from os import environ
from typing import Callable, Dict

import pytest
from asyncpg.pool import Pool
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.db.repositories.articles import ArticlesRepository
from app.db.repositories.comments import CommentsRepository
from app.db.repositories.profiles import ProfilesRepository
from app.db.repositories.users import UsersRepository
from app.models.domain.articles import Article
from app.models.domain.users import UserInDB
from app.services import jwt

REALWORLD_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?Z$")

ARTICLE_KEYS = [
    "createdAt",
    "updatedAt",
    "id",
    "slug",
    "title",
    "description",
    "body",
    "tagList",
    "author",
    "favorited",
    "favoritesCount",
]
PROFILE_KEYS = ["username", "bio", "image", "following"]
USER_KEYS = ["username", "email", "bio", "image", "token"]
COMMENT_KEYS = ["createdAt", "updatedAt", "id", "body", "author"]


@pytest.fixture
async def other_user(pool: Pool) -> UserInDB:
    async with pool.acquire() as conn:
        return await UsersRepository(conn).create_user(
            email="other@test.com", password="other-password", username="other"
        )


@pytest.fixture
def other_token(other_user: UserInDB) -> str:
    return jwt.create_access_token_for_user(other_user, environ["SECRET_KEY"])


@pytest.fixture
def auth_headers(authorization_prefix: str) -> Callable[[str], Dict[str, str]]:
    def factory(token: str) -> Dict[str, str]:
        return {"Authorization": f"{authorization_prefix} {token}"}

    return factory


@pytest.fixture
async def other_follows_test_user(
    test_user: UserInDB, other_user: UserInDB, pool: Pool
) -> None:
    async with pool.acquire() as connection:
        await ProfilesRepository(connection).add_user_into_followers(
            target_user=test_user, requested_user=other_user
        )


@pytest.fixture
async def social_graph(
    test_user: UserInDB,
    test_article: Article,
    other_user: UserInDB,
    other_follows_test_user: None,
    pool: Pool,
) -> None:
    async with pool.acquire() as connection:
        await ArticlesRepository(connection).add_article_into_favorites(
            article=test_article, user=other_user
        )
        await CommentsRepository(connection).create_comment_for_article(
            body="comment by test_user", article=test_article, user=test_user
        )


@pytest.fixture
async def non_raising_client(initialized_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=initialized_app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


def make_token(payload: Dict[str, str], *, secret: str = "", minutes: int = 5) -> str:
    return jwt.create_jwt_token(
        jwt_content=payload,
        secret_key=secret or environ["SECRET_KEY"],
        expires_delta=timedelta(minutes=minutes),
    )
