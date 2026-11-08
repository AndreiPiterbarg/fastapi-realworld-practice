from typing import List

from pydantic import ConfigDict

from app.models.domain.comments import Comment
from app.models.schemas.rwschema import RWSchema


class ListOfCommentsInResponse(RWSchema):
    comments: List[Comment]


class CommentInResponse(RWSchema):
    comment: Comment


class CommentInCreate(RWSchema):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    body: str
