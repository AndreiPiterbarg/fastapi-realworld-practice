"""Publish the same openapi.json the API had on FastAPI 0.79 / pydantic 1.9.

Generated clients and gateways consume this document, so it keeps OpenAPI
3.0.2, plain types for optional values, float bounds and one security entry
per dependency that declares a scheme.
"""
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.security.base import SecurityBase

OPENAPI_VERSION = "3.0.2"
FLOAT_BOUNDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
Requirements = List[Dict[str, List[str]]]


def use_v1_openapi(application: FastAPI) -> None:
    application.openapi_version = OPENAPI_VERSION
    generate = application.openapi

    def openapi() -> Dict[str, Any]:
        if application.openapi_schema is None:
            _to_v1_document(generate(), application)
        return generate()

    application.openapi = openapi  # type: ignore[method-assign]


def _to_v1_document(schema: Dict[str, Any], application: FastAPI) -> None:
    _drop_nullable_any_of(schema)
    for route in application.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            _restore_operations(schema["paths"][route.path_format], route)


def _drop_nullable_any_of(node: Any) -> None:
    if isinstance(node, list):
        for element in node:
            _drop_nullable_any_of(element)
    elif isinstance(node, dict):
        _merge_nullable_any_of(node)
        for nested in node.values():
            _drop_nullable_any_of(nested)


def _merge_nullable_any_of(node: Dict[str, Any]) -> None:
    options = node.get("anyOf", [])
    non_null = [option for option in options if option != {"type": "null"}]
    if len(options) == 2 and len(non_null) == 1:
        node.pop("anyOf")
        node.update(non_null[0])


def _restore_operations(path_item: Dict[str, Any], route: APIRoute) -> None:
    for method in route.methods:
        operation = path_item[method.lower()]
        for parameter in operation.get("parameters", []):
            _float_bounds(parameter["schema"])
        if operation.get("security"):
            operation["security"] = _v1_security(route.dependant, [])


def _float_bounds(parameter_schema: Dict[str, Any]) -> None:
    parameter_schema.update(
        {
            bound: float(limit)
            for bound, limit in parameter_schema.items()
            if bound in FLOAT_BOUNDS
        },
    )


def _v1_security(dependant: Dependant, visited: List[Any]) -> Requirements:
    """Mirror FastAPI 0.79: own schemes first, then sub-dependencies, no repeats."""
    visited.append(dependant.cache_key)
    requirements: Requirements = []
    for security_dependant in dependant.dependencies:
        scheme = security_dependant.call
        if isinstance(scheme, SecurityBase):
            requirements.append(
                {scheme.scheme_name: security_dependant.oauth_scopes},
            )
    for sub_dependant in dependant.dependencies:
        is_scheme = isinstance(sub_dependant.call, SecurityBase)
        if not is_scheme and sub_dependant.cache_key not in visited:
            requirements.extend(_v1_security(sub_dependant, visited))
    return requirements
