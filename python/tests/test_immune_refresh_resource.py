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
    def __init__(self) -> None:
        self.calls: list[str] = []

    def verify_source_snapshot(self, payload: str) -> FakeVerificationResult:
        self.calls.append(payload)
        return FakeVerificationResult()


class FakeCKANClient(CKANClient):
    def __init__(self, result: CKANIngestionResult, matrix: CKANCapabilityMatrix) -> None:
        super().__init__("https://example.test")
        self._result = result
        self._matrix = matrix
        self.probe_calls: list[str | None] = []
        self.ingest_calls: list[dict[str, object]] = []

    def probe_capabilities(self, *, sample_resource_id: str | None = None) -> CKANCapabilityMatrix:
        self.probe_calls.append(sample_resource_id)
        return self._matrix

    def ingest_resource(self, resource_id: str, **kwargs) -> CKANIngestionResult:
        self.ingest_calls.append({"resource_id": resource_id, **kwargs})
        return self._result


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
    )


def make_ingestion_result() -> CKANIngestionResult:
    return CKANIngestionResult(
        resource_id="res-1",
        package_id="pkg-1",
        path="datastore",
        rows=[{"visits": 100, "clicks": 5}],
        fields=[SchemaField(name="visits", field_type="integer"), SchemaField(name="clicks", field_type="integer")],
        resource={"id": "res-1", "package_id": "pkg-1", "datastore_active": True},
        package={"id": "pkg-1", "title": "Growth Hub"},
        attempts=[IngestionAttempt("datastore", True, "selected datastore")],
        metadata={"source": "datastore", "total": 1},
    )


def test_refresh_resource_ingests_and_caches_selected_path() -> None:
    verifier = FakeVerifier()
    client = FakeCKANClient(make_ingestion_result(), make_matrix())
    immune = VeriflowImmuneSystem(client, verifier=verifier, probe_on_startup=False)

    entry = immune.refresh_resource("res-1")

    assert client.probe_calls == ["res-1"]
    assert client.ingest_calls and client.ingest_calls[0]["resource_id"] == "res-1"
    assert entry.ingestion_path == "datastore"
    assert entry.package_id == "pkg-1"
    assert entry.ingestion_metadata["source"] == "datastore"
    assert verifier.calls, "deterministic verification should run on the normalized ingestion rows"
    assert immune.cache["res-1"].rows == [{"visits": 100, "clicks": 5}]


def test_answer_question_auto_refreshes_missing_resource_and_surfaces_ingestion_context() -> None:
    verifier = FakeVerifier()
    client = FakeCKANClient(make_ingestion_result(), make_matrix())
    immune = VeriflowImmuneSystem(client, verifier=verifier, probe_on_startup=False)

    answer = immune.answer_question("res-1", "What is the total clicks?", target_field="clicks")

    assert answer.answer_type == "aggregate_sum"
    assert answer.value == 5.0
    assert answer.evidence["ingestion_path"] == "datastore"
    assert answer.evidence["ingestion_metadata"]["source"] == "datastore"
    assert client.ingest_calls, "answer_question should self-heal by refreshing the resource on cache miss"
