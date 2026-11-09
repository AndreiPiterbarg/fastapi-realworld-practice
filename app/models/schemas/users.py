import re
from decimal import Decimal
from typing import Any, Dict, Match, Optional, Tuple, cast

from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    WithJsonSchema,
)
from pydantic_core import PydanticCustomError
from typing_extensions import Annotated

from app.models.common import check_email_local_part_length
from app.models.domain.users import User
from app.models.schemas.rwschema import RWSchema, V1ModelValidation

# Validation for UserInUpdate.image, kept identical to the pydantic 1.9 HttpUrl
# the API shipped with: same accepted inputs, same stored string (no
# normalisation) and same error type/msg/ctx.
URL_MAX_LENGTH = 2083
URL_MAX_PORT = 65535
URL_ALLOWED_SCHEMES = frozenset(("http", "https"))

_URL_REGEX = re.compile(
    "".join(
        (
            r"(?:(?P<scheme>[a-z][a-z0-9+\-.]+)://)?",
            r"(?:(?P<user>[^\s:/]*)(?::(?P<password>[^\s/]*))?@)?",
            "(?:",
            r"(?P<ipv4>(?:\d{1,3}\.){3}\d{1,3})(?=$|[/:#?])|",
            r"(?P<ipv6>\[[A-F0-9]*:[A-F0-9:]+\])(?=$|[/:#?])|",
            r"(?P<domain>[^\s/:?#]+)",
            ")?",
            r"(?::(?P<port>\d+))?",
            r"(?P<path>/[^\s?#]*)?",
            r"(?:\?(?P<query>[^\s#]*))?",
            r"(?:#(?P<fragment>[^\s#]*))?",
        ),
    ),
    re.IGNORECASE,
)
_ASCII_CHUNK = "[_0-9a-z](?:[-_0-9a-z]{0,61}[_0-9a-z])?"
_ASCII_DOMAIN_REGEX = re.compile(
    r"(?:{0}\.)*?{0}(?P<tld>\.[a-z]{{2,63}})?\.?".format(_ASCII_CHUNK),
    re.IGNORECASE,
)
_INT_CHUNK = "[_0-9a-\U00040000](?:[-_0-9a-\U00040000]{0,61}[_0-9a-\U00040000])?"
_INT_DOMAIN_REGEX = re.compile(
    r"(?:{0}\.)*?{0}(?P<tld>(\.[^\W\d_]{{2,63}})|(\.(?:xn--)[_0-9a-z-]{{2,63}}))?\.?".format(  # noqa: E501
        _INT_CHUNK,
    ),
    re.IGNORECASE,
)

UrlParts = Dict[str, Optional[str]]


def _value_error(
    code: str,
    msg: str,
    ctx: Optional[Dict[str, Any]] = None,
) -> PydanticCustomError:
    return PydanticCustomError("value_error.{0}".format(code), msg, ctx)


class HttpUrlValidator:
    """Port of pydantic 1.9 ``HttpUrl.validate``; returns a plain ``str``."""

    @classmethod
    def validate(cls, value: Any) -> str:  # noqa: WPS110
        url = cls._to_url_str(value)

        # Every group is optional, so the pattern matches any string.
        match = cast(Match[str], _URL_REGEX.match(url))
        parts: UrlParts = match.groupdict()
        cls._check_scheme_and_port(parts)
        host, rebuild = cls._check_host(parts)
        cls._check_extra(url, match.end())
        return cls._build(parts, host) if rebuild else url

    @classmethod
    def _to_url_str(cls, value: Any) -> str:  # noqa: WPS110
        if isinstance(value, (float, int, Decimal)):
            value = str(value)  # noqa: WPS110
        elif not isinstance(value, str):
            raise PydanticCustomError("type_error.str", "str type expected")
        url = value.strip()
        if not url:
            raise _value_error(
                "any_str.min_length",
                "ensure this value has at least {limit_value} characters",
                {"limit_value": 1},
            )
        if len(url) > URL_MAX_LENGTH:
            raise _value_error(
                "any_str.max_length",
                "ensure this value has at most {limit_value} characters",
                {"limit_value": URL_MAX_LENGTH},
            )
        return url

    @classmethod
    def _check_scheme_and_port(cls, parts: UrlParts) -> None:
        scheme = parts["scheme"]
        if scheme is None:
            raise _value_error("url.scheme", "invalid or missing URL scheme")
        if scheme.lower() not in URL_ALLOWED_SCHEMES:
            # A set, as before: the 422 handler cannot JSON-encode it (500).
            raise _value_error(
                "url.scheme",
                "URL scheme not permitted",
                {"allowed_schemes": set(URL_ALLOWED_SCHEMES)},
            )
        port = parts["port"]
        if port is not None and int(port) > URL_MAX_PORT:
            raise _value_error("url.port", "URL port invalid, port cannot exceed 65535")

    @classmethod
    def _check_host(cls, parts: UrlParts) -> Tuple[str, bool]:
        """Return the host to build with and whether the URL must be rebuilt."""
        domain = parts["domain"]
        if domain:
            return cls._check_domain(domain)
        if parts["ipv4"] or parts["ipv6"]:
            return "", False
        raise _value_error("url.host", "URL host invalid")

    @classmethod
    def _check_domain(cls, domain: str) -> Tuple[str, bool]:
        match = _ASCII_DOMAIN_REGEX.fullmatch(domain)
        is_international = match is None or match.group("tld") is None
        if is_international:
            match = _INT_DOMAIN_REGEX.fullmatch(domain)
        if match is None:
            raise _value_error("url.host", "URL host invalid")
        if match.group("tld") is None:
            raise _value_error(
                "url.host",
                "URL host invalid, top level domain required",
            )
        if not is_international:
            return domain, False
        try:
            return domain.encode("idna").decode("ascii"), True
        except UnicodeError as unicode_error:
            raise _value_error("unicode", str(unicode_error))

    @classmethod
    def _check_extra(cls, url: str, end: int) -> None:
        if end != len(url):
            extra = url[end:]
            raise _value_error(
                "url.extra",
                "URL invalid, extra characters found after valid URL: {0!r}".format(
                    extra,
                ),
                {"extra": extra},
            )

    @classmethod
    def _build(cls, parts: UrlParts, host: str) -> str:
        default_port = "80" if parts["scheme"] == "http" else "443"
        userinfo = parts["user"] or ""
        if parts["password"]:
            userinfo = "{0}:{1}".format(userinfo, parts["password"])
        port = parts["port"] or default_port
        return "".join(
            (
                "{0}://".format(parts["scheme"]),
                "{0}@".format(userinfo) if userinfo else "",
                host,
                "" if port == default_port else ":{0}".format(port),
                parts["path"] or "",
                "?{0}".format(parts["query"]) if parts["query"] else "",
                "#{0}".format(parts["fragment"]) if parts["fragment"] else "",
            ),
        )


HttpUrlStr = Annotated[
    str,
    BeforeValidator(HttpUrlValidator.validate),
    WithJsonSchema(
        {
            "type": "string",
            "format": "uri",
            "minLength": 1,
            "maxLength": URL_MAX_LENGTH,
        },
    ),
]


Email = Annotated[EmailStr, AfterValidator(check_email_local_part_length)]


class UserInLogin(RWSchema):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    email: Email
    password: str


class UserInCreate(UserInLogin):
    username: str


class UserInUpdate(V1ModelValidation):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    username: Optional[str] = None
    email: Optional[Email] = None
    password: Optional[str] = None
    bio: Optional[str] = None
    image: Optional[HttpUrlStr] = None


class UserWithToken(User):
    token: str


class UserInResponse(RWSchema):
    user: UserWithToken
