from typing import Any, Dict, Union, cast

from fastapi.exceptions import RequestValidationError
from fastapi.openapi.constants import REF_PREFIX
from fastapi.openapi.utils import (
    validation_error_definition,
    validation_error_response_definition,
)
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.api.errors.v1_errors import pydantic_v1_errors


async def http422_error_handler(
    _: Request,
    exc: Union[RequestValidationError, ValidationError],
) -> JSONResponse:
    return JSONResponse(
        {"errors": pydantic_v1_errors(exc.errors(), getattr(exc, "body", None))},
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
    )


validation_error_response_definition["properties"] = {
    "errors": {
        "title": "Errors",
        "type": "array",
        "items": {"$ref": "{0}ValidationError".format(REF_PREFIX)},
    },
}

validation_error_properties = cast(
    Dict[str, Any],
    validation_error_definition["properties"],
)
for v2_only_property in ("input", "ctx"):
    validation_error_properties.pop(v2_only_property)
