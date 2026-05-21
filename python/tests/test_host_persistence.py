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


class PersistentFakeCKANClient(CKANClient):
    def __init__(self, *, resource: dict, package: dict | None, ingestion: CKANIngestionResult, matrix: CKANCapabilityMatrix) -> None:
        super().__init__("https://example.test")
        self.resource_payload = dict(resource)
        self.package_payload = dict(package) if package else None
        self.ingestion_result = ingestion
        self.matrix = matrix
        self.probe_calls = 0
        self.resource_show_calls = 0
        self.package_show_calls = 0
        self.ingest_calls = 0

    def probe_capabilities(self, *, sample_resource_id: str | None = None) -> CKANCapabilityMatrix:
        self.probe_calls += 1
        return self.matrix

    def resource_show(self, resource_id: str) -> dict:
        self.resource_show_calls += 1
        return {"success": True, "result": dict(self.resource_payload)}

    def package_show(self, package_id: str) -> dict:
        self.package_show_calls += 1
        if self.package_payload is None:
            raise RuntimeError("package not found")
        return {"success": True, "result": dict(self.package_payload)}

    def ingest_resource(self, resource_id: str, **kwargs) -> CKANIngestionResult:
        self.ingest_calls += 1
        return self.ingestion_result


def make_matrix() -> CKANCapabilityMatrix:
    return CKANCapabilityMatrix(
        api_base="https://example.test/api/3/action",
        version=CKANVersion.parse("2.11.4"),
        capabilities={
            "datastore": CapabilityRecord(
                name="datastore",
                state="available",
                source="test",
                detail="fixture",
            )
        },
        supported_actions=["status_show", "resource_show", "package_show", "datastore_info", "datastore_search"],
    )


def make_ingestion() -> CKANIngestionResult:
    return CKANIngestionResult(
        resource_id="res-1",
        package_id="pkg-1",
        path="datastore",
        rows=[{"visits": 100, "clicks": 5}],
        fields=[SchemaField(name="visits", field_type="integer"), SchemaField(name="clicks", field_type="integer")],
        resource={"id": "res-1", "package_id": "pkg-1", "last_modified": "2026-04-08T10:00:00"},
        package={"id": "pkg-1", "title": "Hub", "metadata_modified": "2026-04-08T10:00:00"},
        attempts=[IngestionAttempt("datastore", True, "selected datastore")],
        metadata={"source": "datastore", "total": 1},
    )


def test_bootstrap_reuses_persisted_capability_matrix_across_instances(tmp_path: Path) -> None:
    resource = {"id": "res-1", "package_id": "pkg-1", "last_modified": "2026-04-08T10:00:00"}
    package = {"id": "pkg-1", "metadata_modified": "2026-04-08T10:00:00"}
    client1 = PersistentFakeCKANClient(resource=resource, package=package, ingestion=make_ingestion(), matrix=make_matrix())
    immune1 = VeriflowImmuneSystem(
        client1,
        verifier=FakeVerifier(),
        probe_on_startup=True,
        sample_resource_id="res-1",
        state_dir=tmp_path,
    )

    assert client1.probe_calls == 1
    assert immune1.state_file.exists()

    client2 = PersistentFakeCKANClient(resource=resource, package=package, ingestion=make_ingestion(), matrix=make_matrix())
    immune2 = VeriflowImmuneSystem(
        client2,
        verifier=FakeVerifier(),
        probe_on_startup=True,
        sample_resource_id="res-1",
        state_dir=tmp_path,
    )

    assert client2.probe_calls == 0
    assert immune2.capability_matrix is not None
    assert immune2.capability_matrix.version.raw == "2.11.4"



def test_refresh_resource_skips_ingestion_until_upstream_fingerprint_changes(tmp_path: Path) -> None:
    resource = {"id": "res-1", "package_id": "pkg-1", "last_modified": "2026-04-08T10:00:00"}
    package = {"id": "pkg-1", "metadata_modified": "2026-04-08T10:00:00"}
    client = PersistentFakeCKANClient(resource=resource, package=package, ingestion=make_ingestion(), matrix=make_matrix())
    immune = VeriflowImmuneSystem(
        client,
        verifier=FakeVerifier(),
        probe_on_startup=False,
        state_dir=tmp_path,
    )

    first = immune.refresh_resource("res-1")
    first_fingerprint = first.upstream_fingerprint
    second = immune.refresh_resource("res-1")

    assert first.digest == second.digest
    assert client.ingest_calls == 1

    client.resource_payload = {"id": "res-1", "package_id": "pkg-1", "last_modified": "2026-04-08T11:00:00"}
    third = immune.refresh_resource("res-1")

    assert third.upstream_fingerprint != first_fingerprint
    assert client.ingest_calls == 2
