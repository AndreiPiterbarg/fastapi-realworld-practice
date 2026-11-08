from typing import Any

from pydantic import BeforeValidator
from pydantic_core import PydanticCustomError


def _parse_int_like_pydantic_v1(raw_value: Any) -> Any:
    # Mobile clients rely on pydantic 1's int() parsing of query/path params:
    # "1.0" is rejected and unicode digits such as "５" are accepted.
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        raise PydanticCustomError(
            "int_parsing",
            "Input should be a valid integer, unable to parse string as an integer",
        )


# Place after Query()/Path() inside Annotated so it runs before the int and
# ge checks, and the OpenAPI schema keeps "minimum".
V1_INT_PARSING = BeforeValidator(_parse_int_like_pydantic_v1)
