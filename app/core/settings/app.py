import logging
import re
import sys
from typing import Annotated, Any, Dict, List, Optional, Tuple

from loguru import logger
from pydantic import (
    AfterValidator,
    BeforeValidator,
    PostgresDsn,
    SecretStr,
    TypeAdapter,
)
from pydantic_settings import SettingsConfigDict

from app.core.logging import InterceptHandler
from app.core.settings.base import BaseAppSettings

_postgres_dsn_adapter = TypeAdapter(PostgresDsn)

# pydantic v1 AnyUrl regexes, used to rebuild DSNs exactly as v1 did.
_V1_URL_REGEX = re.compile(
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
_V1_ASCII_CHUNK = "[_0-9a-z](?:[-_0-9a-z]{0,61}[_0-9a-z])?"
_V1_ASCII_DOMAIN_REGEX = re.compile(
    r"(?:{0}\.)*?{0}(?P<tld>\.[a-z]{{2,63}})?\.?".format(_V1_ASCII_CHUNK),
    re.IGNORECASE,
)


def _strip_dsn(dsn: Any) -> Any:
    return dsn.strip() if isinstance(dsn, str) else dsn


def _v1_keeps_input(domain: Optional[str]) -> bool:
    ascii_domain = domain and _V1_ASCII_DOMAIN_REGEX.fullmatch(domain)
    return not domain or bool(ascii_domain and ascii_domain.group("tld"))


def _v1_build(parts: Dict[str, Optional[str]], host: str) -> str:
    return "".join(
        (
            "{0}://".format(parts["scheme"]),
            parts["user"] or "",
            ":{0}".format(parts["password"]) if parts["password"] else "",
            "@" if parts["user"] or parts["password"] else "",
            host.encode("idna").decode("ascii"),
            ":{0}".format(parts["port"]) if parts["port"] else "",
            parts["path"] or "",
            "?{0}".format(parts["query"]) if parts["query"] else "",
            "#{0}".format(parts["fragment"]) if parts["fragment"] else "",
        ),
    )


def _v1_dsn_string(dsn: str) -> str:
    """Return the str that pydantic v1's PostgresDsn held for ``dsn``.

    v1 kept the input, except for domains that are non-ASCII or have no TLD:
    those were IDNA-encoded and the URL rebuilt from its parts.
    """
    parts = _V1_URL_REGEX.match(dsn).groupdict()  # type: ignore[union-attr]
    domain = parts["domain"]
    return dsn if _v1_keeps_input(domain) else _v1_build(parts, domain or "")


def _validate_postgres_dsn(dsn: str) -> str:
    _postgres_dsn_adapter.validate_python(dsn)
    return _v1_dsn_string(dsn)


# Validated as PostgresDsn but kept as the str pydantic v1 produced (the
# stripped input, IDNA host rebuild aside), so asyncpg and alembic receive
# exactly what they did before.
PostgresDsnStr = Annotated[
    str,
    BeforeValidator(_strip_dsn),
    AfterValidator(_validate_postgres_dsn),
]


class AppSettings(BaseAppSettings):
    debug: bool = False
    docs_url: str = "/docs"
    openapi_prefix: str = ""
    openapi_url: str = "/openapi.json"
    redoc_url: str = "/redoc"
    title: str = "FastAPI example application"
    version: str = "0.0.0"

    database_url: PostgresDsnStr
    max_connection_count: int = 10
    min_connection_count: int = 10

    secret_key: SecretStr

    api_prefix: str = "/api"

    jwt_token_prefix: str = "Token"

    allowed_hosts: List[str] = ["*"]

    logging_level: int = logging.INFO
    loggers: Tuple[str, str] = ("uvicorn.asgi", "uvicorn.access")

    # pydantic v1 coerced numbers to str (e.g. ALLOWED_HOSTS=[1, 2]); keep that.
    model_config = SettingsConfigDict(
        validate_assignment=True,
        coerce_numbers_to_str=True,
    )

    @property
    def fastapi_kwargs(self) -> Dict[str, Any]:
        return {
            "debug": self.debug,
            "docs_url": self.docs_url,
            "openapi_prefix": self.openapi_prefix,
            "openapi_url": self.openapi_url,
            "redoc_url": self.redoc_url,
            "title": self.title,
            "version": self.version,
        }

    def configure_logging(self) -> None:
        logging.getLogger().handlers = [InterceptHandler()]
        for logger_name in self.loggers:
            logging_logger = logging.getLogger(logger_name)
            logging_logger.handlers = [InterceptHandler(level=self.logging_level)]

        logger.configure(handlers=[{"sink": sys.stderr, "level": self.logging_level}])
