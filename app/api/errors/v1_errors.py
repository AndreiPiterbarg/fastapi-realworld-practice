"""Render pydantic v2 validation errors in the pydantic 1.9 wire format.

The mobile clients parse the 422 body that pydantic 1.9 produced, so each v2
error is translated back to its v1 ``loc``/``msg``/``type``/``ctx``. Errors
with no v1 equivalent keep their own ``msg``/``type``/``ctx`` in the v1 shape.
"""
import json
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

ErrorDict = Dict[str, Any]
Ctx = Dict[str, Any]
V1Error = Tuple[str, str, Optional[Ctx]]
Translator = Callable[[ErrorDict, Ctx, Any], V1Error]

JSON_DECODE_CTX_KEYS = ("msg", "doc", "pos", "lineno", "colno")

NONE_NOT_ALLOWED: V1Error = (
    "none is not an allowed value",
    "type_error.none.not_allowed",
    None,
)


def pydantic_v1_errors(errors: Sequence[Any], body: Any = None) -> List[ErrorDict]:
    return [_to_v1_error(error, body) for error in errors]


def _to_v1_error(error: ErrorDict, body: Any) -> ErrorDict:
    msg, error_type, ctx = _translate(error, body)
    v1_error: ErrorDict = {"loc": list(error["loc"]), "msg": msg, "type": error_type}
    if ctx is not None:
        v1_error["ctx"] = ctx
    return v1_error


def _translate(error: ErrorDict, body: Any) -> V1Error:
    ctx = error.get("ctx")
    translate = _TRANSLATORS.get(error["type"])
    if translate is None:
        return error["msg"], error["type"], ctx
    return translate(error, ctx or {}, body)


class _V2Errors(object):
    def missing(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        return "field required", "value_error.missing", None

    def int_parsing(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        return "value is not a valid integer", "type_error.integer", None

    def greater_than_equal(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        limit = ctx["ge"]
        return (
            "ensure this value is greater than or equal to {0}".format(limit),
            "value_error.number.not_ge",
            {"limit_value": limit},
        )

    def string_type(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        if error.get("input") is None:
            return NONE_NOT_ALLOWED
        return "str type expected", "type_error.str", None

    def list_type(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        if error.get("input") is None:
            return NONE_NOT_ALLOWED
        return "value is not a valid list", "type_error.list", None

    def json_invalid(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        # FastAPI passes the decoded request text (JSONDecodeError.doc) as body.
        position = error["loc"][-1]
        decode_error = json.JSONDecodeError(ctx["error"], body, position)
        v1_ctx = {key: getattr(decode_error, key) for key in JSON_DECODE_CTX_KEYS}
        return str(decode_error), "value_error.jsondecode", v1_ctx

    def value_error(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        # Only EmailStr (and the email local-part check) raise it in request models.
        return "value is not a valid email address", "value_error.email", None


_v2_errors = _V2Errors()
_TRANSLATORS: Mapping[str, Translator] = MappingProxyType(
    {
        "missing": _v2_errors.missing,
        "int_parsing": _v2_errors.int_parsing,
        "greater_than_equal": _v2_errors.greater_than_equal,
        "string_type": _v2_errors.string_type,
        "list_type": _v2_errors.list_type,
        "json_invalid": _v2_errors.json_invalid,
        "value_error": _v2_errors.value_error,
    },
)
