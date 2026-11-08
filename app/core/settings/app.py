import logging
import sys
from typing import Annotated, Any, Dict, List, Tuple

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


def _strip_dsn(dsn: Any) -> Any:
    return dsn.strip() if isinstance(dsn, str) else dsn


def _validate_postgres_dsn(dsn: str) -> str:
    _postgres_dsn_adapter.validate_python(dsn)
    return dsn


# Validated as PostgresDsn but kept as the configured string (stripped), like
# pydantic v1, so asyncpg and alembic receive exactly what was configured.
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
