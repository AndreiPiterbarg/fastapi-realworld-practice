"""Golden contracts for 422 bodies the pydantic-v1 shim rebuilds.

Expected bodies were taken from the pydantic 1.9 app (old main) and pin
`none is not an allowed value`, `str type expected` and
`value is not a valid list` for embedded request bodies.
"""
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from app.models.domain.articles import Article

pytestmark = pytest.mark.asyncio

NONE_NOT_ALLOWED = {
    "msg": "none is not an allowed value",
    "type": "type_error.none.not_allowed",
}
STR_EXPECTED = {"msg": "str type expected", "type": "type_error.str"}
NOT_A_LIST = {"msg": "value is not a valid list", "type": "type_error.list"}


def _error(loc: List[Any], error: Dict[str, str]) -> Dict[str, Any]:
    return {"loc": loc, **error}


@pytest.mark.parametrize(
    "article, expected_errors",
    (
        (
            {"title": None, "description": [], "body": {}, "tagList": "abc"},
            [
                _error(["body", "article", "title"], NONE_NOT_ALLOWED),
                _error(["body", "article", "description"], STR_EXPECTED),
                _error(["body", "article", "body"], STR_EXPECTED),
                _error(["body", "article", "tagList"], NOT_A_LIST),
            ],
        ),
        (
            {"title": "t", "description": "d", "body": "b", "tagList": None},
            [_error(["body", "article", "tagList"], NONE_NOT_ALLOWED)],
        ),
        (
            {"title": "t", "description": "d", "body": "b", "tagList": {"a": 1}},
            [_error(["body", "article", "tagList"], NOT_A_LIST)],
        ),
    ),
)
async def test_create_article_type_errors_422(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    article: Dict[str, Any],
    expected_errors: List[Dict[str, Any]],
) -> None:
    response = await authorized_client.post(
        app.url_path_for("articles:create-article"),
        json={"article": article},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json() == {"errors": expected_errors}


@pytest.mark.parametrize(
    "comment_body, expected_error",
    ((None, NONE_NOT_ALLOWED), ([], STR_EXPECTED)),
)
async def test_create_comment_type_errors_422(  # pydantic-v1 contract
    app: FastAPI,
    authorized_client: AsyncClient,
    test_article: Article,
    comment_body: Any,
    expected_error: Dict[str, str],
) -> None:
    response = await authorized_client.post(
        app.url_path_for(
            "comments:create-comment-for-article",
            slug=test_article.slug,
        ),
        json={"comment": {"body": comment_body}},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json() == {
        "errors": [_error(["body", "comment", "body"], expected_error)],
    }


async def test_login_null_credentials_422(  # pydantic-v1 contract
    app: FastAPI,
    client: AsyncClient,
) -> None:
    response = await client.post(
        app.url_path_for("auth:login"),
        json={"user": {"email": None, "password": None}},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json() == {
        "errors": [
            _error(["body", "user", "email"], NONE_NOT_ALLOWED),
            _error(["body", "user", "password"], NONE_NOT_ALLOWED),
        ],
    }
