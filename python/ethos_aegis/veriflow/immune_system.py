from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    from ethos_aegis.agent.scaffolds.task_verifier_mesh import DeterministicVerifier
except ModuleNotFoundError:
    class _PortableVerificationResult:
        def __init__(self, passed: bool = True, issue_type: str = "") -> None:
            self.passed = passed
            self.issue_type = issue_type

    class DeterministicVerifier:  # type: ignore[override]
        def verify_source_snapshot(self, payload: str) -> _PortableVerificationResult:
            return _PortableVerificationResult()

from .ckan_adapter import (
    CKANCapabilityMatrix,
    CKANClient,
    CKANIngestionResult,
    CKANVersion,
    CapabilityRecord,
    IngestionAttempt,
    ProbeEvidence,
    SchemaField,
)
from .question_answering import AnswerRecord, VeriflowReasoner


@dataclass(slots=True)
class DatasetCacheEntry:
    resource_id: str
    digest: str
    rows: list[dict[str, Any]]
    fields: list[SchemaField]
    package_id: str | None = None
    ingestion_path: str = "unknown"
    ingestion_attempts: list[IngestionAttempt] = field(default_factory=list)
    ingestion_metadata: dict[str, Any] = field(default_factory=dict)
    resource_snapshot: dict[str, Any] = field(default_factory=dict)
    package_snapshot: dict[str, Any] | None = None
    upstream_fingerprint: str | None = None
    upstream_fingerprint_payload: dict[str, Any] = field(default_factory=dict)
    last_answer: Optional[AnswerRecord] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "digest": self.digest,
            "rows": self.rows,
            "fields": [
                {
                    "name": field.name,
                    "label": field.label,
                    "description": field.description,
                    "aliases": list(field.aliases),
                    "unit": field.unit,
                    "field_type": field.field_type,
                }
                for field in self.fields
            ],
            "package_id": self.package_id,
            "ingestion_path": self.ingestion_path,
            "ingestion_attempts": [
                {"path": attempt.path, "ok": attempt.ok, "detail": attempt.detail}
                for attempt in self.ingestion_attempts
            ],
            "ingestion_metadata": dict(self.ingestion_metadata),
            "resource_snapshot": dict(self.resource_snapshot),
            "package_snapshot": dict(self.package_snapshot) if self.package_snapshot else None,
            "upstream_fingerprint": self.upstream_fingerprint,
            "upstream_fingerprint_payload": dict(self.upstream_fingerprint_payload),
        }


class VeriflowImmuneSystem:
    """
    Agentic data immune system for CKAN-backed knowledge hubs.

    Default fingerprinting policy:
    - use fingerprint_mode="auto" for most hosts
    - use fingerprint_mode="datastore_lightweight" explicitly when row-level freshness matters more than probe cost
    """

    def __init__(
        self,
        ckan: CKANClient,
        verifier: DeterministicVerifier | None = None,
        reasoner: VeriflowReasoner | None = None,
        *,
        probe_on_startup: bool = True,
        sample_resource_id: str | None = None,
        persist_host_state: bool = True,
        state_dir: str | Path | None = None,
        fingerprint_mode: str = "auto",
        row_signature_limit: int = 10,
        row_signature_fields: list[str] | None = None,
    ) -> None:
        self.ckan = ckan
        self.verifier = verifier or DeterministicVerifier()
        self.reasoner = reasoner or VeriflowReasoner()
        self._cache: dict[str, DatasetCacheEntry] = {}
        self._capability_matrix: CKANCapabilityMatrix | None = None
        self._probe_sample_resource_id = sample_resource_id
        self.fingerprint_mode = fingerprint_mode
        self.row_signature_limit = row_signature_limit
        self.row_signature_fields = list(row_signature_fields) if row_signature_fields else None
        self._persist_host_state = persist_host_state
        self._state_dir = Path(state_dir) if state_dir is not None else Path(tempfile.gettempdir()) / "ethos_aegis_veriflow_state"
        self._state: dict[str, Any] = self._load_state() if persist_host_state else {"host": self.ckan.base_url, "resources": {}}
        if probe_on_startup:
            self.bootstrap(sample_resource_id=sample_resource_id)

    @property
    def capability_matrix(self) -> CKANCapabilityMatrix | None:
        return self._capability_matrix

    @property
    def cache(self) -> Mapping[str, DatasetCacheEntry]:
        return self._cache

    @property
    def state_file(self) -> Path:
        return self._state_dir / f"{self._host_key()}.json"

    def _host_key(self) -> str:
        return hashlib.sha256(self.ckan.base_url.encode("utf-8")).hexdigest()[:16]

    def _load_state(self) -> dict[str, Any]:
        path = self.state_file
        if not path.exists():
            return {"host": self.ckan.base_url, "resources": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"host": self.ckan.base_url, "resources": {}}
        if not isinstance(payload, dict):
            return {"host": self.ckan.base_url, "resources": {}}
        payload.setdefault("host", self.ckan.base_url)
        payload.setdefault("resources", {})
        return payload

    def _save_state(self) -> None:
        if not self._persist_host_state:
            return
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")

    def _matrix_from_dict(self, payload: Mapping[str, Any]) -> CKANCapabilityMatrix:
        version_payload = payload.get("version") or {}
        version = CKANVersion(
            raw=str(version_payload.get("raw") or "unknown"),
            major=version_payload.get("major"),
            minor=version_payload.get("minor"),
            patch=version_payload.get("patch"),
            prerelease=version_payload.get("prerelease"),
        )
        capabilities: dict[str, CapabilityRecord] = {}
        for name, record_payload in (payload.get("capabilities") or {}).items():
            evidence = [
                ProbeEvidence(
                    name=str(item.get("name") or ""),
                    ok=bool(item.get("ok")),
                    source=str(item.get("source") or ""),
                    detail=str(item.get("detail") or ""),
                    status_code=item.get("status_code"),
                )
                for item in (record_payload.get("evidence") or [])
                if isinstance(item, Mapping)
            ]
            capabilities[str(name)] = CapabilityRecord(
                name=str(name),
                state=str(record_payload.get("state") or "unavailable"),
                source=str(record_payload.get("source") or "state_cache"),
                detail=str(record_payload.get("detail") or ""),
                evidence=evidence,
            )
        return CKANCapabilityMatrix(
            api_base=str(payload.get("api_base") or f"{self.ckan.base_url}/api/3/action"),
            version=version,
            capabilities=capabilities,
            discovered_plugins=list(payload.get("discovered_plugins") or []),
            supported_actions=list(payload.get("supported_actions") or []),
            status_payload=dict(payload.get("status_payload") or {}),
        )

    def _persist_capability_matrix(self, matrix: CKANCapabilityMatrix) -> None:
        self._state["capability_matrix"] = matrix.to_dict()
        self._state["probe_sample_resource_id"] = self._probe_sample_resource_id
        self._save_state()

    def _persist_resource_manifest(self, entry: DatasetCacheEntry) -> None:
        resources = self._state.setdefault("resources", {})
        resources[entry.resource_id] = {
            "upstream_fingerprint": entry.upstream_fingerprint,
            "upstream_fingerprint_payload": dict(entry.upstream_fingerprint_payload),
            "ingestion_digest": entry.digest,
            "package_id": entry.package_id,
            "ingestion_path": entry.ingestion_path,
            "ingestion_metadata": dict(entry.ingestion_metadata),
        }
        self._save_state()

    def bootstrap(self, *, sample_resource_id: str | None = None, force: bool = False) -> CKANCapabilityMatrix:
        sample = sample_resource_id or self._probe_sample_resource_id
        persisted = self._state.get("capability_matrix")
        persisted_sample = self._state.get("probe_sample_resource_id")
        if not force and self._capability_matrix is not None:
            if sample and sample != self._probe_sample_resource_id:
                force = True
            else:
                return self._capability_matrix
        if not force and persisted and (sample == persisted_sample or sample is None or persisted_sample is None):
            matrix = self._matrix_from_dict(persisted)
            self._capability_matrix = matrix
            self._probe_sample_resource_id = sample or persisted_sample
            return matrix
        matrix = self.ckan.probe_capabilities(sample_resource_id=sample)
        self._capability_matrix = matrix
        self._probe_sample_resource_id = sample
        self._persist_capability_matrix(matrix)
        return matrix

    def _stable_digest(self, rows: list[dict[str, Any]]) -> str:
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()

    def _fallback_fingerprint_from_ingestion(self, result: CKANIngestionResult) -> tuple[str, dict[str, Any]]:
        payload = {
            "mode": f"{self.fingerprint_mode}:fallback",
            "resource": result.resource,
            "package": result.package or {},
            "path": result.path,
            "rows_digest": self._stable_digest(result.rows),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest(), payload

    def refresh_resource(self, resource_id: str) -> DatasetCacheEntry:
        if self._capability_matrix is None or (self._probe_sample_resource_id is None and resource_id):
            self.bootstrap(sample_resource_id=resource_id, force=self._probe_sample_resource_id is None and bool(resource_id))

        existing = self._cache.get(resource_id)
        manifest = (self._state.get("resources") or {}).get(resource_id) if self._persist_host_state else None

        resource_dict: dict[str, Any] | None = None
        package_dict: dict[str, Any] | None = None
        upstream_fingerprint: str | None = None
        upstream_payload: dict[str, Any] = {}

        try:
            upstream_fingerprint, upstream_payload, resource_dict, package_dict = self.ckan.compute_upstream_fingerprint(
                resource_id,
                capability_matrix=self._capability_matrix,
                fingerprint_mode=self.fingerprint_mode,
                row_signature_limit=self.row_signature_limit,
                row_signature_fields=self.row_signature_fields,
            )
        except Exception:
            upstream_fingerprint = None
            upstream_payload = {}
            resource_dict = None
            package_dict = None

        if (
            existing is not None
            and upstream_fingerprint is not None
            and existing.upstream_fingerprint == upstream_fingerprint
        ):
            return existing

        if (
            existing is None
            and manifest
            and upstream_fingerprint is not None
            and manifest.get("upstream_fingerprint") == upstream_fingerprint
        ):
            # Fast path for a fresh process: metadata/fingerprint did not change, but we still need rows locally.
            # Re-ingest once to hydrate the in-memory cache from the current authoritative path.
            pass

        result = self.ckan.ingest_resource(
            resource_id,
            capability_matrix=self._capability_matrix,
            resource_dict=resource_dict,
            package_dict=package_dict,
        )

        if upstream_fingerprint is None:
            upstream_fingerprint, upstream_payload = self._fallback_fingerprint_from_ingestion(result)
            resource_dict = dict(result.resource)
            package_dict = dict(result.package) if result.package else None

        verification = self.verifier.verify_source_snapshot(json.dumps(result.rows, sort_keys=True))
        if not verification.passed and getattr(verification, "issue_type", "") == "syntax_error":
            raise ValueError("Dataset cache failed deterministic serialization verification.")

        entry = DatasetCacheEntry(
            resource_id=resource_id,
            digest=self._stable_digest(result.rows),
            rows=result.rows,
            fields=result.fields,
            package_id=result.package_id,
            ingestion_path=result.path,
            ingestion_attempts=result.attempts,
            ingestion_metadata=dict(result.metadata),
            resource_snapshot=dict(resource_dict or result.resource),
            package_snapshot=dict(package_dict or result.package) if (package_dict or result.package) else None,
            upstream_fingerprint=upstream_fingerprint,
            upstream_fingerprint_payload=dict(upstream_payload),
        )
        self._cache[resource_id] = entry
        self._persist_resource_manifest(entry)
        return entry

    def answer_question(self, resource_id: str, question: str, *, target_field: str | None = None) -> AnswerRecord:
        if resource_id not in self._cache:
            self.refresh_resource(resource_id)
        if self._capability_matrix is None:
            self.bootstrap(sample_resource_id=resource_id)
        entry = self._cache[resource_id]
        answer = self.reasoner.answer(
            question,
            entry.rows,
            entry.fields,
            target_field=target_field,
            capability_matrix=self._capability_matrix,
        )
        answer.evidence.setdefault("ingestion_path", entry.ingestion_path)
        answer.evidence.setdefault("ingestion_metadata", dict(entry.ingestion_metadata))
        answer.evidence.setdefault("upstream_fingerprint_mode", entry.upstream_fingerprint_payload.get("mode", self.fingerprint_mode))
        entry.last_answer = answer
        return answer
