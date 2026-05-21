from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ethos_aegis.veriflow.ckan_adapter import (  # noqa: E402
    CKANCapabilityMatrix,
    CKANClient,
    CKANVersion,
    CapabilityRecord,
)


class FakeCKANClient(CKANClient):
    def __init__(self, *, resource: dict, package: dict | None = None, datastore_info_result: dict | None = None, datastore_search_result: dict | None = None, matrix: CKANCapabilityMatrix | None = None) -> None:
        super().__init__("https://example.test")
        self._resource = resource
        self._package = package
        self._datastore_info_result = datastore_info_result
        self._datastore_search_result = datastore_search_result
        self._matrix = matrix

    def probe_capabilities(self, *, sample_resource_id: str | None = None) -> CKANCapabilityMatrix:
        return self._matrix or make_matrix(datastore=False)

    def resource_show(self, resource_id: str) -> dict:
        return {"success": True, "result": dict(self._resource)}

    def package_show(self, package_id: str) -> dict:
        if self._package is None:
            raise RuntimeError("package not found")
        return {"success": True, "result": dict(self._package)}

    def datastore_info(self, resource_id: str) -> dict:
        if self._datastore_info_result is None:
            raise RuntimeError("datastore unavailable")
        return {"success": True, "result": dict(self._datastore_info_result)}

    def datastore_search(self, resource_id: str, **kwargs) -> dict:
        if self._datastore_search_result is None:
            raise RuntimeError("datastore unavailable")
        return {"success": True, "result": dict(self._datastore_search_result)}


def make_matrix(*, datastore: bool) -> CKANCapabilityMatrix:
    return CKANCapabilityMatrix(
        api_base="https://example.test/api/3/action",
        version=CKANVersion.parse("2.11.4"),
        capabilities={
            "datastore": CapabilityRecord(
                name="datastore",
                state="available" if datastore else "unavailable",
                source="test",
                detail="fixture",
            )
        },
    )


def test_ingest_resource_prefers_datastore_when_available() -> None:
    client = FakeCKANClient(
        resource={"id": "res-1", "package_id": "pkg-1", "datastore_active": True},
        package={"id": "pkg-1", "resources": []},
        datastore_info_result={"fields": [{"id": "visits", "type": "int"}, {"id": "clicks", "type": "int"}]},
        datastore_search_result={"records": [{"visits": 100, "clicks": 5}], "total": 1},
        matrix=make_matrix(datastore=True),
    )

    result = client.ingest_resource("res-1")

    assert result.path == "datastore"
    assert result.rows == [{"visits": 100, "clicks": 5}]
    assert [field.name for field in result.fields] == ["visits", "clicks"]
    assert result.attempts[-1].path == "datastore"
    assert result.attempts[-1].ok is True


def test_ingest_resource_falls_back_to_resource_schema_when_datastore_fails() -> None:
    client = FakeCKANClient(
        resource={
            "id": "res-2",
            "package_id": "pkg-2",
            "datastore_active": True,
            "schema": [{"name": "impressions", "type": "int"}, {"name": "ctr", "type": "float"}],
            "records": [{"impressions": 1000, "ctr": 0.12}],
        },
        package={"id": "pkg-2", "resources": []},
        datastore_info_result=None,
        datastore_search_result=None,
        matrix=make_matrix(datastore=True),
    )

    result = client.ingest_resource("res-2")

    assert result.path == "resource_schema"
    assert result.rows == [{"impressions": 1000, "ctr": 0.12}]
    assert [field.name for field in result.fields] == ["impressions", "ctr"]
    assert result.attempts[0].path == "datastore"
    assert result.attempts[0].ok is False
    assert result.attempts[-1].path == "resource_schema"


def test_ingest_resource_uses_metadata_fallback_without_datastore_or_schema() -> None:
    client = FakeCKANClient(
        resource={
            "id": "res-3",
            "package_id": "pkg-3",
            "name": "Quarterly Metrics",
            "format": "CSV",
            "size": 2048,
            "position": 1,
            "datastore_active": False,
        },
        package={
            "id": "pkg-3",
            "title": "Marketing Hub",
            "license_id": "cc-by",
            "num_resources": 4,
        },
        matrix=make_matrix(datastore=False),
    )

    result = client.ingest_resource("res-3")

    assert result.path == "metadata_fallback"
    assert result.rows and result.rows[0]["resource_size"] == 2048
    assert result.rows[0]["package_num_resources"] == 4
    assert {field.name for field in result.fields} >= {"resource_size", "package_num_resources"}
