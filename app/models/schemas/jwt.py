from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.common import CoercedStr


class JWTMeta(BaseModel):
    exp: datetime
    sub: str


class JWTUser(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    username: CoercedStr
