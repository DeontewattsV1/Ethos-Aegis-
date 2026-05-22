from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ethos_aegis.veriflow.ckan_adapter import (  # noqa: E402
    CKANCapabilityMatrix,
    CKANClient,
    CKANIngestionResult,
    CKANVersion,
    CapabilityRecord,
    IngestionAttempt,
    SchemaField,
)
from ethos_aegis.veriflow.immune_system import VeriflowImmuneSystem  # noqa: E402


@dataclass
class FakeVerificationResult:
    passed: bool = True
    issue_type: str = ""


class FakeVerifier:
    def verify_source_snapshot(self, payload: str) -> FakeVerificationResult:
        return FakeVerificationResult()


class RowMutatingCKANClient(CKANClient):
    def __init__(self) -> None:
        super().__init__("https://example.test")
        self.resource_payload = {"id": "res-1", "package_id": "pkg-1", "last_modified": "2026-04-08T10:00:00", "datastore_active": True}
        self.package_payload = {"id": "pkg-1", "metadata_modified": "2026-04-08T10:00:00"}
        self.rows = [{"visits": 100, "clicks": 5}]
        self.ingest_calls = 0

    def probe_capabilities(self, *, sample_resource_id: str | None = None) -> CKANCapabilityMatrix:
        return CKANCapabilityMatrix(
            api_base="https://example.test/api/3/action",
            version=CKANVersion.parse("2.11.4"),
            capabilities={
                "datastore": CapabilityRecord(name="datastore", state="available", source="test", detail="fixture")
            },
        )

    def resource_show(self, resource_id: str) -> dict:
        return {"success": True, "result": dict(self.resource_payload)}

    def package_show(self, package_id: str) -> dict:
        return {"success": True, "result": dict(self.package_payload)}

    def datastore_info(self, resource_id: str) -> dict:
        return {"success": True, "result": {"fields": [{"id": "visits", "type": "int"}, {"id": "clicks", "type": "int"}]}}

    def datastore_search(self, resource_id: str, **kwargs) -> dict:
        limit = kwargs.get("limit", 100)
        return {"success": True, "result": {"records": [dict(r) for r in self.rows[:limit]], "total": len(self.rows)}}

    def ingest_resource(self, resource_id: str, **kwargs) -> CKANIngestionResult:
        self.ingest_calls += 1
        return CKANIngestionResult(
            resource_id="res-1",
            package_id="pkg-1",
            path="datastore",
            rows=[dict(r) for r in self.rows],
            fields=[SchemaField(name="visits", field_type="integer"), SchemaField(name="clicks", field_type="integer")],
            resource=dict(self.resource_payload),
            package=dict(self.package_payload),
            attempts=[IngestionAttempt("datastore", True, "selected datastore")],
            metadata={"source": "datastore", "total": len(self.rows)},
        )


def test_datastore_lightweight_fingerprint_reingests_when_rows_change_without_metadata_change(tmp_path: Path) -> None:
    client = RowMutatingCKANClient()
    immune = VeriflowImmuneSystem(
        client,
        verifier=FakeVerifier(),
        probe_on_startup=False,
        state_dir=tmp_path,
        fingerprint_mode="datastore_lightweight",
        row_signature_limit=5,
    )

    first = immune.refresh_resource("res-1")
    first_fingerprint = first.upstream_fingerprint
    second = immune.refresh_resource("res-1")
    assert second.upstream_fingerprint == first_fingerprint
    assert client.ingest_calls == 1

    client.rows = [{"visits": 100, "clicks": 7}]
    third = immune.refresh_resource("res-1")
    assert third.upstream_fingerprint != first_fingerprint
    assert client.ingest_calls == 2
    assert third.rows[0]["clicks"] == 7
