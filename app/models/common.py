import datetime
from typing import Any

from pydantic import BaseModel, BeforeValidator, Field, field_validator
from typing_extensions import Annotated


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


def str_from_bool(value: Any) -> Any:  # noqa: WPS110
    """pydantic 1.9's ``str_validator`` also turned a bool into "True"/"False"."""
    if isinstance(value, bool):
        return str(value)
    return value


# A ``str`` field as pydantic 1.9 validated it, together with
# ``coerce_numbers_to_str=True`` on the model for int/float/Decimal.
CoercedStr = Annotated[str, BeforeValidator(str_from_bool)]
