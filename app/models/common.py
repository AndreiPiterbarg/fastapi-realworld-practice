import datetime

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

# email-validator 1.x always rejected a local part over 64 chars; 2.x only
# does so with strict=True, which pydantic does not pass.
EMAIL_LOCAL_PART_MAX_LENGTH = 64


class DateTimeModelMixin(BaseModel):
    created_at: datetime.datetime = None  # type: ignore
    updated_at: datetime.datetime = None  # type: ignore

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def default_datetime(
        cls,
        value: datetime.datetime,  # noqa: WPS110
    ) -> datetime.datetime:
        return value or datetime.datetime.now()


class IDModelMixin(BaseModel):
    id_: int = Field(0, alias="id")


def check_email_local_part_length(email: str) -> str:
    excess = len(email.rsplit("@", 1)[0]) - EMAIL_LOCAL_PART_MAX_LENGTH
    if excess > 0:
        plural = "s" if excess > 1 else ""
        too_many = "{0} character{1} too many".format(excess, plural)
        reason = "The email address is too long before the @-sign ({0}).".format(
            too_many,
        )
        raise PydanticCustomError(
            "value_error",
            "value is not a valid email address: {reason}",
            {"reason": reason},
        )
    return email
