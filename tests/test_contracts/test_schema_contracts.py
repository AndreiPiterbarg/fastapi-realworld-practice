"""Golden contracts for pydantic schemas (pydantic 1.9 behaviour).

Entries marked ``# pydantic-v1 contract`` are values that pydantic v2 produces
differently by default. They can reach clients, so the migration must keep them.
"""
import datetime
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.errors.v1_errors import pydantic_v1_errors
from app.models.common import DateTimeModelMixin
from app.models.domain.profiles import Profile
from app.models.domain.rwmodel import (
    convert_datetime_to_realworld,
    convert_field_to_camel_case,
)
from app.models.schemas.articles import (
    ArticleForResponse,
    ArticleInCreate,
    ArticlesFilters,
)
from app.models.schemas.users import UserInResponse, UserInUpdate, UserWithToken

FIXED_DT = datetime.datetime(2020, 1, 2, 3, 4, 5, 6)


def v1_errors(exc: ValidationError) -> list:
    # The v1-shaped errors the 422 handler sends, with tuple locs as in v1.
    return [
        {**error, "loc": tuple(error["loc"])}
        for error in pydantic_v1_errors(exc.errors())
    ]


def v1_json(model: object, **kwargs: object) -> str:
    # pydantic v1 .json(): json.dumps of the JSON-mode dict, default separators.
    return json.dumps(model.model_dump(mode="json", **kwargs))  # type: ignore


# --- RWModel serialization --------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    (
        (
            datetime.datetime(2019, 10, 27, 2, 21, 42, 844640),
            "2019-10-27T02:21:42.844640Z",
        ),
        (datetime.datetime(2019, 10, 27, 2, 21, 42), "2019-10-27T02:21:42Z"),
        (
            datetime.datetime(2019, 10, 27, 2, 21, 42, 5, tzinfo=datetime.timezone.utc),
            "2019-10-27T02:21:42.000005Z",
        ),
        # Current behaviour that looks like a bug: a non-UTC offset is replaced,
        # not converted, so the wall-clock time is kept and labelled as UTC.
        (
            datetime.datetime(
                2019,
                10,
                27,
                2,
                21,
                42,
                tzinfo=datetime.timezone(datetime.timedelta(hours=3)),
            ),
            "2019-10-27T02:21:42Z",
        ),
    ),
)
def test_convert_datetime_to_realworld(value: datetime.datetime, expected: str) -> None:
    assert convert_datetime_to_realworld(value) == expected


@pytest.mark.parametrize(
    "field, alias",
    (
        ("tags", "tags"),
        ("created_at", "createdAt"),
        ("favorites_count", "favoritesCount"),
        ("articles_count", "articlesCount"),
        ("id_", "id"),
        ("a_b_c", "aBC"),
    ),
)
def test_camel_case_alias_generator(field: str, alias: str) -> None:
    assert convert_field_to_camel_case(field) == alias


# --- ArticleInCreate --------------------------------------------------------


def test_article_in_create_accepts_alias() -> None:
    article = ArticleInCreate(title="t", description="d", body="b", tagList=["a"])

    assert article.tags == ["a"]


def test_article_in_create_accepts_field_name() -> None:
    article = ArticleInCreate(title="t", description="d", body="b", tags=["a"])

    assert article.tags == ["a"]


def test_article_in_create_alias_wins_over_field_name() -> None:
    article = ArticleInCreate(
        title="t", description="d", body="b", tags=["name"], tagList=["alias"]
    )

    assert article.tags == ["alias"]


def test_article_in_create_tags_default_to_empty_list() -> None:
    article = ArticleInCreate(title="t", description="d", body="b")

    assert article.model_dump() == {
        "title": "t",
        "description": "d",
        "body": "b",
        "tags": [],
    }
    assert article.model_dump(by_alias=True)["tagList"] == []


def test_article_in_create_ignores_unknown_fields() -> None:
    article = ArticleInCreate(title="t", description="d", body="b", slug="nope")

    assert article.model_dump() == {
        "title": "t",
        "description": "d",
        "body": "b",
        "tags": [],
    }


def test_article_in_create_coerces_int_title_to_str() -> None:
    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert ArticleInCreate(title=1, description="d", body="b").title == "1"


def test_article_in_create_missing_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArticleInCreate()

    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert v1_errors(exc_info.value) == [
        {"loc": ("title",), "msg": "field required", "type": "value_error.missing"},
        {
            "loc": ("description",),
            "msg": "field required",
            "type": "value_error.missing",
        },
        {"loc": ("body",), "msg": "field required", "type": "value_error.missing"},
    ]


def test_article_in_create_rejects_string_tag_list() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArticleInCreate(title="t", description="d", body="b", tagList="abc")

    # pydantic-v1 contract: v2 default differs; migration must preserve this
    assert v1_errors(exc_info.value) == [
        {
            "loc": ("tagList",),
            "msg": "value is not a valid list",
            "type": "type_error.list",
        }
    ]


# --- UserInUpdate -----------------------------------------------------------


def test_user_in_update_empty_body_is_valid() -> None:
    assert UserInUpdate().model_dump() == {
        "username": None,
        "email": None,
        "password": None,
        "bio": None,
        "image": None,
    }


@pytest.mark.parametrize(
    "url, expected",
    (
        # pydantic-v1 contract: v2 adds a trailing slash; migration must preserve this
        ("https://example.com", "https://example.com"),
        ("https://example.com/", "https://example.com/"),
        ("http://example.com/a/b.png", "http://example.com/a/b.png"),
        # pydantic-v1 contract: v2 lowercases scheme/host; migration must preserve this
        ("HTTPS://Example.COM/a/b?x=1", "HTTPS://Example.COM/a/b?x=1"),
    ),
)
def test_user_in_update_image_serialization(url: str, expected: str) -> None:
    update = UserInUpdate(image=url)

    assert isinstance(update.image, str)
    assert str(update.image) == expected
    assert update.model_dump()["image"] == expected
    assert v1_json(update) == (
        '{"username": null, "email": null, "password": null, "bio": null, '
        f'"image": "{expected}"}}'
    )


@pytest.mark.parametrize(
    "url, expected_error",
    (
        (
            "not a url",
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            {
                "loc": ("image",),
                "msg": "invalid or missing URL scheme",
                "type": "value_error.url.scheme",
            },
        ),
        (
            "ftp://example.com",
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            {
                "loc": ("image",),
                "msg": "URL scheme not permitted",
                "type": "value_error.url.scheme",
                "ctx": {"allowed_schemes": {"http", "https"}},
            },
        ),
        (
            "https://",
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            {
                "loc": ("image",),
                "msg": "URL host invalid",
                "type": "value_error.url.host",
            },
        ),
    ),
)
def test_user_in_update_image_rejects_non_url(url: str, expected_error: dict) -> None:
    with pytest.raises(ValidationError) as exc_info:
        UserInUpdate(image=url)

    assert v1_errors(exc_info.value) == [expected_error]


def test_user_in_update_email_normalises_domain_only() -> None:
    assert UserInUpdate(email="Foo@Example.COM").email == "Foo@example.com"


# --- DateTimeModelMixin -----------------------------------------------------


def test_datetime_mixin_fills_explicit_none() -> None:
    before = datetime.datetime.now()
    model = DateTimeModelMixin(created_at=None, updated_at=None)
    after = datetime.datetime.now()

    assert before <= model.created_at <= after
    assert before <= model.updated_at <= after
    assert model.created_at.tzinfo is None


@pytest.mark.parametrize("falsy", ("", 0))
def test_datetime_mixin_fills_falsy_values(falsy: object) -> None:
    model = DateTimeModelMixin(created_at=falsy)

    assert isinstance(model.created_at, datetime.datetime)


def test_datetime_mixin_leaves_omitted_fields_none() -> None:
    # Current behaviour that looks like a bug: the validator has no
    # always=True, so omitted timestamps stay None instead of "now".
    model = DateTimeModelMixin()

    assert model.created_at is None
    assert model.updated_at is None


def test_datetime_mixin_keeps_given_values() -> None:
    model = DateTimeModelMixin(created_at=FIXED_DT, updated_at="2020-01-01T00:00:00Z")

    assert model.created_at == FIXED_DT
    assert model.updated_at == datetime.datetime(
        2020, 1, 1, tzinfo=datetime.timezone.utc
    )


def test_datetime_mixin_rejects_garbage() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DateTimeModelMixin(created_at="nope")

    # Not reachable from a request (no body accepts createdAt/updatedAt), so
    # this pins pydantic's own error rather than a 422 body.
    assert exc_info.value.errors(include_url=False) == [
        {
            "loc": ("created_at",),
            "msg": "Input should be a valid datetime or date, input is too short",
            "type": "datetime_from_date_parsing",
            "input": "nope",
            "ctx": {"error": "input is too short"},
        }
    ]


# --- ArticlesFilters --------------------------------------------------------


def test_articles_filters_defaults() -> None:
    assert ArticlesFilters().model_dump() == {
        "tag": None,
        "author": None,
        "favorited": None,
        "limit": 20,
        "offset": 0,
    }


def test_articles_filters_boundaries_accepted() -> None:
    filters = ArticlesFilters(limit=1, offset=0)

    assert (filters.limit, filters.offset) == (1, 0)


def test_articles_filters_coerces_numeric_strings() -> None:
    assert ArticlesFilters(limit="5").limit == 5


@pytest.mark.parametrize(
    "kwargs, expected_error",
    (
        (
            {"limit": 0},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            {
                "loc": ("limit",),
                "msg": "ensure this value is greater than or equal to 1",
                "type": "value_error.number.not_ge",
                "ctx": {"limit_value": 1},
            },
        ),
        (
            {"offset": -1},
            # pydantic-v1 contract: v2 default differs; migration must preserve this
            {
                "loc": ("offset",),
                "msg": "ensure this value is greater than or equal to 0",
                "type": "value_error.number.not_ge",
                "ctx": {"limit_value": 0},
            },
        ),
    ),
)
def test_articles_filters_boundaries_rejected(
    kwargs: dict, expected_error: dict
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArticlesFilters(**kwargs)

    assert v1_errors(exc_info.value) == [expected_error]


# --- orm_mode ---------------------------------------------------------------


def _orm_article(**overrides: object) -> SimpleNamespace:
    attributes = {
        "id": 5,
        "created_at": FIXED_DT,
        "updated_at": FIXED_DT,
        "slug": "s",
        "title": "t",
        "description": "d",
        "body": "b",
        "tags": ["x"],
        "author": Profile(username="a"),
        "favorited": True,
        "favorites_count": 3,
    }
    attributes.update(overrides)
    return SimpleNamespace(**attributes)


def test_article_for_response_from_orm() -> None:
    article = ArticleForResponse.model_validate(_orm_article())

    assert article.id_ == 5
    assert article.tags == ["x"]
    assert v1_json(article, by_alias=True) == (
        '{"createdAt": "2020-01-02T03:04:05.000006Z", '
        '"updatedAt": "2020-01-02T03:04:05.000006Z", "id": 5, "slug": "s", '
        '"title": "t", "description": "d", "body": "b", "tagList": ["x"], '
        '"author": {"username": "a", "bio": "", "image": null, "following": false}, '
        '"favorited": true, "favoritesCount": 3}'
    )


def test_article_for_response_from_orm_reads_tag_list_alias() -> None:
    orm = _orm_article()
    del orm.tags
    orm.tagList = ["y"]

    assert ArticleForResponse.model_validate(orm).tags == ["y"]


def test_article_for_response_from_orm_prefers_id_attribute() -> None:
    assert ArticleForResponse.model_validate(_orm_article(id_=7)).id_ == 5


def test_article_for_response_from_orm_rejects_plain_object_author() -> None:
    # Nested Profile is not orm_mode, so only models/dicts are accepted.
    author = SimpleNamespace(username="a", bio="", image=None, following=False)

    with pytest.raises(ValidationError) as exc_info:
        ArticleForResponse.model_validate(_orm_article(author=author))

    # Response models are built server-side; a failure here is a 500, not a
    # 422 body, so this pins pydantic's own error.
    assert exc_info.value.errors(include_url=False, include_input=False) == [
        {
            "loc": ("author",),
            "msg": "Input should be a valid dictionary or instance of Profile",
            "type": "model_type",
            "ctx": {"class_name": "Profile"},
        }
    ]


def test_user_in_response_from_orm() -> None:
    user = UserWithToken(username="u", email="e", token="t")

    response = UserInResponse.model_validate(SimpleNamespace(user=user))

    assert v1_json(response) == (
        '{"user": {"username": "u", "email": "e", "bio": "", "image": null, '
        '"token": "t"}}'
    )


def test_user_in_response_from_orm_accepts_nested_dict() -> None:
    orm = SimpleNamespace(user={"username": "u", "email": "e", "token": "t"})

    assert UserInResponse.model_validate(orm).model_dump() == {
        "user": {"username": "u", "email": "e", "bio": "", "image": None, "token": "t"}
    }


def test_user_in_response_from_orm_rejects_plain_object_user() -> None:
    orm = SimpleNamespace(
        user=SimpleNamespace(username="u", email="e", bio="", image=None, token="t")
    )

    with pytest.raises(ValidationError) as exc_info:
        UserInResponse.model_validate(orm)

    # Response models are built server-side; a failure here is a 500, not a
    # 422 body, so this pins pydantic's own error.
    assert exc_info.value.errors(include_url=False, include_input=False) == [
        {
            "loc": ("user",),
            "msg": "Input should be a valid dictionary or instance of UserWithToken",
            "type": "model_type",
            "ctx": {"class_name": "UserWithToken"},
        }
    ]
