"""Golden contract: openapi.json is the document old main served.

``golden/openapi_v1.json`` was recorded from old main (FastAPI 0.79.1,
pydantic 1.9.2) with ``APP_ENV=test``. Generated iOS/Android/web clients and
gateways read this document. Key order is not compared; value types are, so
``1.0`` and ``1`` differ.
"""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

GOLDEN_OPENAPI = Path(__file__).parent / "golden" / "openapi_v1.json"


def _canonical(document: object) -> str:
    return json.dumps(document, sort_keys=True)


async def test_openapi_document_matches_old_main(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    expected = json.loads(GOLDEN_OPENAPI.read_text())

    first = await client.get(app.openapi_url)
    second = await client.get(app.openapi_url)

    assert first.status_code == second.status_code == 200
    assert _canonical(first.json()) == _canonical(expected)
    assert _canonical(second.json()) == _canonical(expected)
