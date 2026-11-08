"""Render pydantic v2 validation errors in the pydantic 1.9 wire format.

The mobile clients parse the 422 body that pydantic 1.9 produced, so each v2
error is translated back to its v1 ``loc``/``msg``/``type``/``ctx``. Errors
with no v1 equivalent keep their own ``msg``/``type``/``ctx`` in the v1 shape.
"""
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

ErrorDict = Dict[str, Any]
Ctx = Dict[str, Any]
V1Error = Tuple[str, str, Optional[Ctx]]
Translator = Callable[[ErrorDict, Ctx, Any], Optional[V1Error]]

URL_MAX_LENGTH = 2083
JSON_DECODE_CTX_KEYS = ("msg", "doc", "pos", "lineno", "colno")
EMAIL_INVALID_MSG = "value is not a valid email address"

NONE_NOT_ALLOWED: V1Error = (
    "none is not an allowed value",
    "type_error.none.not_allowed",
    None,
)
STR_EXPECTED: V1Error = ("str type expected", "type_error.str", None)
URL_SCHEME_MISSING: V1Error = (
    "invalid or missing URL scheme",
    "value_error.url.scheme",
    None,
)
URL_HOST_INVALID: V1Error = ("URL host invalid", "value_error.url.host", None)
URL_EMPTY: V1Error = (
    "ensure this value has at least 1 characters",
    "value_error.any_str.min_length",
    {"limit_value": 1},
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
    translated = translate(error, ctx or {}, body) if translate else None
    return translated or (error["msg"], error["type"], ctx)


class _ScalarErrors(object):
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
        return NONE_NOT_ALLOWED if error.get("input") is None else STR_EXPECTED

    def list_type(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        if error.get("input") is None:
            return NONE_NOT_ALLOWED
        return "value is not a valid list", "type_error.list", None

    def json_invalid(self, error: ErrorDict, ctx: Ctx, body: Any) -> Optional[V1Error]:
        if not isinstance(body, str):
            return None
        position = error["loc"][-1]
        decode_error = json.JSONDecodeError(ctx["error"], body, position)
        v1_ctx = {key: getattr(decode_error, key) for key in JSON_DECODE_CTX_KEYS}
        return str(decode_error), "value_error.jsondecode", v1_ctx

    def value_error(self, error: ErrorDict, ctx: Ctx, body: Any) -> Optional[V1Error]:
        if "reason" in ctx:  # raised by EmailStr
            return EMAIL_INVALID_MSG, "value_error.email", None
        raised = ctx.get("error")
        if isinstance(raised, ValueError):
            return str(raised), "value_error", None
        return None


class _UrlErrors(object):
    def url_too_long(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        return self._max_length(ctx["max_length"])

    def url_scheme(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        # pydantic 1.9 put a set here, which the 422 handler cannot JSON-encode.
        allowed_schemes = set(re.findall("'([^']*)'", ctx["expected_schemes"]))
        return (
            "URL scheme not permitted",
            "value_error.url.scheme",
            {"allowed_schemes": allowed_schemes},
        )

    def url_type(self, error: ErrorDict, ctx: Ctx, body: Any) -> V1Error:
        url = error.get("input")
        if url is None:
            return NONE_NOT_ALLOWED
        if not isinstance(url, (int, float)):
            return STR_EXPECTED
        # pydantic 1.9 coerced numbers to str, which never contain a scheme.
        if len(str(url)) > URL_MAX_LENGTH:
            return self._max_length(URL_MAX_LENGTH)
        return URL_SCHEME_MISSING

    def url_parsing(self, error: ErrorDict, ctx: Ctx, body: Any) -> Optional[V1Error]:
        return _URL_PARSING_ERRORS.get(ctx["error"])

    def _max_length(self, limit: int) -> V1Error:
        return (
            "ensure this value has at most {0} characters".format(limit),
            "value_error.any_str.max_length",
            {"limit_value": limit},
        )


_URL_PARSING_ERRORS: Mapping[str, V1Error] = MappingProxyType(
    {
        "relative URL without a base": URL_SCHEME_MISSING,
        "empty host": URL_HOST_INVALID,
        "invalid IPv6 address": URL_HOST_INVALID,
        "input is empty": URL_EMPTY,
    },
)

_scalar_errors = _ScalarErrors()
_url_errors = _UrlErrors()
_TRANSLATORS: Mapping[str, Translator] = MappingProxyType(
    {
        "missing": _scalar_errors.missing,
        "int_parsing": _scalar_errors.int_parsing,
        "greater_than_equal": _scalar_errors.greater_than_equal,
        "string_type": _scalar_errors.string_type,
        "list_type": _scalar_errors.list_type,
        "json_invalid": _scalar_errors.json_invalid,
        "value_error": _scalar_errors.value_error,
        "url_too_long": _url_errors.url_too_long,
        "url_scheme": _url_errors.url_scheme,
        "url_type": _url_errors.url_type,
        "url_parsing": _url_errors.url_parsing,
    },
)
