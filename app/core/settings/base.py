from enum import Enum
from typing import Any, Dict, Tuple, Type

from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class AppEnvTypes(Enum):
    prod = "prod"
    dev = "dev"
    test = "test"


class DeclaredFieldsDotEnvSource(PydanticBaseSettingsSource):
    """Read env files but skip keys that are not settings fields.

    Env files also hold keys for other tools (e.g. POSTGRES_USER), which must be
    ignored, while unknown init kwargs are still rejected (extra="forbid").
    """

    def __init__(
        self,
        settings_cls: Type[BaseSettings],
        dotenv_settings: PydanticBaseSettingsSource,
    ) -> None:
        super().__init__(settings_cls)
        self._dotenv_settings = dotenv_settings

    def __call__(self) -> Dict[str, Any]:
        return {
            field_name: field_value
            for field_name, field_value in self._dotenv_settings().items()
            if field_name in self.settings_cls.model_fields
        }

    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> Tuple[Any, str, bool]:
        # Abstract in the base class; unused because __call__ is overridden.
        return self._dotenv_settings.get_field_value(  # pragma: no cover
            field,
            field_name,
        )


class BaseAppSettings(BaseSettings):
    app_env: AppEnvTypes = AppEnvTypes.prod

    model_config = SettingsConfigDict(env_file=".env")

    @classmethod
    def settings_customise_sources(  # noqa: WPS211
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            DeclaredFieldsDotEnvSource(settings_cls, dotenv_settings),
            file_secret_settings,
        )
