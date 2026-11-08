import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    field_serializer,
)


def convert_datetime_to_realworld(dt: datetime.datetime) -> str:
    return dt.replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def convert_field_to_camel_case(string: str) -> str:
    return "".join(
        word if index == 0 else word.capitalize()
        for index, word in enumerate(string.split("_"))
    )


class RWModel(BaseModel):
    model_config = ConfigDict(
        validate_by_name=True,
        alias_generator=convert_field_to_camel_case,
    )

    # No return annotation: one would replace every field's OpenAPI output schema.
    @field_serializer("*", mode="wrap", when_used="json")
    def serialize_datetime_to_realworld(  # type: ignore[no-untyped-def]
        self,
        value: object,  # noqa: WPS110
        serialize: SerializerFunctionWrapHandler,
    ):
        if isinstance(value, datetime.datetime):
            return convert_datetime_to_realworld(value)
        return serialize(value)
