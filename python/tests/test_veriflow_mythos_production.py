"""Production Mythos-VeriFlow authorization, environment and persistence regressions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ethos_aegis.mythos_runtime import (
    AuthorizationDenied,
    ExecutionGrantSigner,
    ExecutionGrantVerifier,
    MythosVeriflowRuntime,
    RetentionPolicy,
    StateIntegrityError,
    TrustedEnvironment,
)
from ethos_aegis.veriflow.ckan_adapter import (
    CKANCapabilityMatrix,
    CKANClient,
    CKANIngestionResult,
    CKANVersion,
    CapabilityRecord,
    IngestionAttempt,
    SchemaField,
)
from ethos_aegis.veriflow.immune_system import VeriflowImmuneSystem


NOW = datetime.now(timezone.utc)
AUTH_KEY = b"a" * 32
PERSIST_KEY = b"p" * 32
REVISION = "a" * 40


@dataclass
class FakeVerificationResult:
    passed: bool = True
    issue_type: str = ""


class FakeVerifier:
    def verify_source_snapshot(self, payload: str) -> FakeVerificationResult:
        return FakeVerificationResult()


class FakeCKANClient(CKANClient):
    def __init__(self) -> None:
        super().__init__("https://example.test")
        self.probe_calls = 0
        self.ingest_calls = 0
        self.rows = [{"visits": 100, "clicks": 5}]

    def probe_capabilities(self, *, sample_resource_id: str | None = None) -> CKANCapabilityMatrix:
        self.probe_calls += 1
        return CKANCapabilityMatrix(
            api_base="https://example.test/api/3/action",
            version=CKANVersion.parse("2.11.4"),
            capabilities={
                "datastore": CapabilityRecord(name="datastore", state="available", source="test", detail="fixture")
            },
        )

    def resource_show(self, resource_id: str) -> dict:
        return {"success": True, "result": {"id": resource_id, "package_id": "pkg-1", "datastore_active": True}}

    def package_show(self, package_id: str) -> dict:
        return {"success": True, "result": {"id": package_id, "title": "Growth Hub"}}

    def datastore_info(self, resource_id: str) -> dict:
        return {"success": True, "result": {"fields": [{"id": "visits"}, {"id": "clicks"}]}}

    def datastore_search(self, resource_id: str, **kwargs) -> dict:
        return {"success": True, "result": {"records": [dict(row) for row in self.rows], "total": len(self.rows)}}

    def ingest_resource(self, resource_id: str, **kwargs) -> CKANIngestionResult:
        self.ingest_calls += 1
        return CKANIngestionResult(
            resource_id=resource_id,
            package_id="pkg-1",
            path="datastore",
            rows=[dict(row) for row in self.rows],
            fields=[SchemaField(name="visits", field_type="integer"), SchemaField(name="clicks", field_type="integer")],
            resource={"id": resource_id, "package_id": "pkg-1", "datastore_active": True},
            package={"id": "pkg-1", "title": "Growth Hub"},
            attempts=[IngestionAttempt("datastore", True, "selected datastore")],
            metadata={"source": "datastore", "total": len(self.rows)},
        )


def environment(*, target: str = "ckan-production", revision: str = REVISION) -> TrustedEnvironment:
    return TrustedEnvironment("trusted-service", target, "https://example.test", revision)


def runtime(tmp_path: Path, *, env: TrustedEnvironment | None = None, retention: RetentionPolicy | None = None) -> MythosVeriflowRuntime:
    return MythosVeriflowRuntime(
        environment=env or environment(),
        grant_verifier=ExecutionGrantVerifier(AUTH_KEY),
        persistence_key=PERSIST_KEY,
        state_dir=tmp_path / "assurance",
        retention=retention,
    )


def grant(env: TrustedEnvironment | None = None) -> str:
    return ExecutionGrantSigner(AUTH_KEY).issue(
        subject="service://veriflow",
        purposes=("capability_probe", "dataset_refresh", "question_answer"),
        actions=("veriflow.probe", "veriflow.refresh", "veriflow.answer"),
        resources=("res-1",),
        environment=env or environment(),
        ttl_seconds=300,
    )


def test_production_bridge_automatically_gates_and_records_veriflow(tmp_path: Path) -> None:
    client = FakeCKANClient()
    bridge = runtime(tmp_path)
    immune = VeriflowImmuneSystem(
        client,
        verifier=FakeVerifier(),
        sample_resource_id="res-1",
        mythos_runtime=bridge,
        execution_grant=grant(),
    )

    answer = immune.answer_question("res-1", "What is total clicks?", target_field="clicks")

    assert answer.value == 5.0
    assert client.probe_calls == 1
    assert client.ingest_calls == 1
    events = bridge.ledger.events()
    assert bridge.ledger.verify()
    assert {"veriflow.probe", "veriflow.refresh", "veriflow.answer"}.issubset({event["action"] for event in events})

    stored = json.loads(immune.state_file.read_text(encoding="utf-8"))
    cache = stored["payload"]["resources"]["res-1"]["cache_entry"]
    assert "mythos_state_envelope" in stored
    assert cache["rows_persisted"] is False
    assert cache["rows"] == []
    assert cache["row_count"] == 1


def test_production_bridge_denies_before_network_without_grant(tmp_path: Path) -> None:
    client = FakeCKANClient()
    bridge = runtime(tmp_path)
    immune = VeriflowImmuneSystem(client, verifier=FakeVerifier(), probe_on_startup=False, mythos_runtime=bridge)

    with pytest.raises(AuthorizationDenied):
        immune.refresh_resource("res-1")

    assert client.probe_calls == 0
    assert client.ingest_calls == 0
    assert bridge.ledger.events()[-1]["decision"] == "DENY"


def test_grant_is_bound_to_trusted_target_environment(tmp_path: Path) -> None:
    client = FakeCKANClient()
    bridge = runtime(tmp_path)
    immune = VeriflowImmuneSystem(
        client,
        verifier=FakeVerifier(),
        probe_on_startup=False,
        mythos_runtime=bridge,
        execution_grant=grant(environment(target="different-production")),
    )

    with pytest.raises(AuthorizationDenied):
        immune.refresh_resource("res-1")
    assert client.probe_calls == 0


def test_tampered_production_state_fails_closed(tmp_path: Path) -> None:
    client = FakeCKANClient()
    bridge = runtime(tmp_path)
    immune = VeriflowImmuneSystem(
        client,
        verifier=FakeVerifier(),
        probe_on_startup=False,
        mythos_runtime=bridge,
        execution_grant=grant(),
    )
    immune.refresh_resource("res-1")

    stored = json.loads(immune.state_file.read_text(encoding="utf-8"))
    stored["payload"]["host"] = "https://tampered.invalid"
    immune.state_file.write_text(json.dumps(stored), encoding="utf-8")

    with pytest.raises(StateIntegrityError):
        VeriflowImmuneSystem(
            FakeCKANClient(),
            verifier=FakeVerifier(),
            probe_on_startup=False,
            mythos_runtime=runtime(tmp_path),
            execution_grant=grant(),
        )


def test_evidence_retention_is_bounded_and_chain_remains_valid(tmp_path: Path) -> None:
    retention = RetentionPolicy(
        max_events=3,
        max_age_seconds=60,
        resource_state_ttl_seconds=60,
        max_resources=10,
        max_state_bytes=1024 * 1024,
    )
    bridge = runtime(tmp_path, retention=retention)
    token = ExecutionGrantSigner(AUTH_KEY).issue(
        subject="service://veriflow",
        purposes=("dataset_refresh",),
        actions=("veriflow.refresh",),
        resources=("res-1",),
        environment=environment(),
        ttl_seconds=300,
        now=NOW,
    )
    for offset in range(5):
        bridge.authorize(
            token,
            action="veriflow.refresh",
            resource_id="res-1",
            purpose="dataset_refresh",
            now=NOW + timedelta(seconds=offset),
        )
    assert len(bridge.ledger.events()) == 3
    assert bridge.ledger.verify()
