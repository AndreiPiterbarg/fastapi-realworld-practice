from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.common import CoercedStr
from app.models.domain.articles import Article
from app.models.schemas.rwschema import RWSchema

DEFAULT_ARTICLES_LIMIT = 20
DEFAULT_ARTICLES_OFFSET = 0


class ArticleForResponse(RWSchema, Article):
    tags: List[str] = Field(..., alias="tagList")


class ArticleInResponse(RWSchema):
    article: ArticleForResponse


class ArticleInCreate(RWSchema):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    title: CoercedStr
    description: CoercedStr
    body: CoercedStr
    tags: List[CoercedStr] = Field([], alias="tagList")


class ArticleInUpdate(RWSchema):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    title: Optional[CoercedStr] = None
    description: Optional[CoercedStr] = None
    body: Optional[CoercedStr] = None


class ListOfArticlesInResponse(RWSchema):
    articles: List[ArticleForResponse]
    articles_count: int


class ArticlesFilters(BaseModel):
    tag: Optional[str] = None
    author: Optional[str] = None
    favorited: Optional[str] = None
    limit: int = Field(DEFAULT_ARTICLES_LIMIT, ge=1)
    offset: int = Field(DEFAULT_ARTICLES_OFFSET, ge=0)
