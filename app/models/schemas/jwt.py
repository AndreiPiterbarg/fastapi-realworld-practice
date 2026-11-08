from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JWTMeta(BaseModel):
    exp: datetime
    sub: str


class JWTUser(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    username: str
