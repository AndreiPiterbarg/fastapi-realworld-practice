from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, ModelWrapValidatorHandler, model_validator
from pydantic_core import PydanticCustomError

from app.models.domain.rwmodel import RWModel

# JSON values pydantic 2 rejects as a model but pydantic 1.9 validated (bool is int).
V1_NON_OBJECT_INPUTS = (str, int, float, list)
_MISSING = object()


class V1ModelValidation(BaseModel):
    """Validate non-object input the way pydantic 1.9's ``BaseModel.validate`` did.

    Mobile clients rely on it for embedded bodies such as ``{"user": []}``:
    orm_mode models read each field as an attribute of the value, other models
    use ``dict(value)``.
    """

    @model_validator(mode="wrap")
    @classmethod
    def validate_like_pydantic_v1(
        cls,
        value: Any,  # noqa: WPS110
        validate: ModelWrapValidatorHandler["V1ModelValidation"],
    ) -> "V1ModelValidation":
        if not isinstance(value, V1_NON_OBJECT_INPUTS):
            return validate(value)
        if cls.model_config.get("from_attributes"):
            return validate(cls._read_attributes(value))
        return validate(_to_dict(value))

    @classmethod
    def _read_attributes(cls, source: Any) -> Dict[str, Any]:
        attributes = {}
        for name, field in cls.model_fields.items():
            for key in dict.fromkeys((field.alias or name, name)):
                attribute = getattr(source, key, _MISSING)
                if attribute is not _MISSING:
                    attributes[key] = attribute
                    break
        return attributes


def _to_dict(source: Any) -> Dict[str, Any]:
    try:
        as_dict = dict(source)
    except (TypeError, ValueError):
        raise PydanticCustomError("type_error.dict", "value is not a valid dict")
    if not all(isinstance(key, str) for key in as_dict):
        # pydantic 1.9 reported the TypeError from ``cls(**as_dict)``.
        raise PydanticCustomError("type_error", "keywords must be strings")
    return as_dict


class RWSchema(RWModel, V1ModelValidation):
    model_config = ConfigDict(from_attributes=True)
