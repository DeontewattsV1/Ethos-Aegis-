
from __future__ import annotations

import hashlib
import json
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

from .ckan_adapter import CKANCapabilityMatrix, CKANClient, CKANIngestionResult, IngestionAttempt, SchemaField
from .question_answering import AnswerRecord, VeriflowReasoner


@dataclass(slots=True)
class DatasetCacheEntry:
    resource_id: str
    digest: str
    rows: list[dict[str, Any]]
    fields: list[SchemaField]
    package_id: str | None = None
    upstream_fingerprint: str | None = None
    upstream_fingerprint_payload: dict[str, Any] = field(default_factory=dict)
    ingestion_path: str = "unknown"
    ingestion_attempts: list[IngestionAttempt] = field(default_factory=list)
    ingestion_metadata: dict[str, Any] = field(default_factory=dict)
    resource_snapshot: dict[str, Any] = field(default_factory=dict)
    package_snapshot: dict[str, Any] | None = None
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
            "upstream_fingerprint": self.upstream_fingerprint,
            "upstream_fingerprint_payload": dict(self.upstream_fingerprint_payload),
            "ingestion_path": self.ingestion_path,
            "ingestion_attempts": [
                {"path": attempt.path, "ok": attempt.ok, "detail": attempt.detail}
                for attempt in self.ingestion_attempts
            ],
            "ingestion_metadata": dict(self.ingestion_metadata),
            "resource_snapshot": dict(self.resource_snapshot),
            "package_snapshot": dict(self.package_snapshot) if self.package_snapshot else None,
        }


class VeriflowImmuneSystem:
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
        fingerprint_mode: str = "metadata",
        row_signature_limit: int = 10,
        row_signature_fields: list[str] | None = None,
    ) -> None:
        self.ckan = ckan
        self.verifier = verifier or DeterministicVerifier()
        self.reasoner = reasoner or VeriflowReasoner()
        self._cache: dict[str, DatasetCacheEntry] = {}
        self._capability_matrix: CKANCapabilityMatrix | None = None
        self._probe_sample_resource_id = sample_resource_id
        self.persist_host_state = persist_host_state
        self.state_dir = Path(state_dir) if state_dir is not None else Path("/mnt/data/veriflow_state")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprint_mode = fingerprint_mode
        self.row_signature_limit = row_signature_limit
        self.row_signature_fields = list(row_signature_fields) if row_signature_fields else None
        self._host_state = self._load_host_state()
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
        key = hashlib.sha256(self.ckan.base_url.encode("utf-8")).hexdigest()[:20]
        return self.state_dir / f"ckan_host_{key}.json"

    def bootstrap(self, *, sample_resource_id: str | None = None, force: bool = False) -> CKANCapabilityMatrix:
        sample = sample_resource_id or self._probe_sample_resource_id
        if not force and self._capability_matrix is not None:
            if sample and sample != self._probe_sample_resource_id:
                force = True
            else:
                return self._capability_matrix

        if not force:
            persisted = self._load_capability_matrix_from_state(sample)
            if persisted is not None:
                self._capability_matrix = persisted
                self._probe_sample_resource_id = sample or self._host_state.get("probe_sample_resource_id")
                return persisted

        matrix = self.ckan.probe_capabilities(sample_resource_id=sample)
        self._capability_matrix = matrix
        self._probe_sample_resource_id = sample
        self._host_state["capability_matrix"] = matrix.to_dict()
        self._host_state["probe_sample_resource_id"] = sample
        self._save_host_state()
        return matrix

    def refresh_resource(
        self,
        resource_id: str,
        *,
        package_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        field_names: list[str] | None = None,
        force: bool = False,
    ) -> DatasetCacheEntry:
        matrix = self.bootstrap(
            sample_resource_id=resource_id,
            force=force or self._capability_matrix is None or self._probe_sample_resource_id is None,
        )
        resource_snapshot = None
        package_snapshot = None
        upstream_fingerprint = None
        fingerprint_payload: dict[str, Any] = {}
        fingerprint_ready = False
        try:
            upstream_fingerprint, fingerprint_payload, resource_snapshot, package_snapshot = self.ckan.compute_upstream_fingerprint(
                resource_id,
                capability_matrix=matrix,
                package_id=package_id,
                fingerprint_mode=self.fingerprint_mode,
                row_signature_limit=self.row_signature_limit,
                row_signature_fields=self.row_signature_fields,
            )
            fingerprint_ready = True
        except Exception:
            fingerprint_ready = False

        persisted_entry = self._host_state.setdefault("resources", {}).get(resource_id, {})
        existing = self._cache.get(resource_id)
        if fingerprint_ready and not force and existing and existing.upstream_fingerprint == upstream_fingerprint:
            return existing
        if fingerprint_ready and not force and not existing and persisted_entry.get("upstream_fingerprint") == upstream_fingerprint and persisted_entry.get("cache_entry"):
            restored = self._dataset_entry_from_dict(persisted_entry["cache_entry"])
            self._cache[resource_id] = restored
            return restored

        ingest_kwargs = {
            "package_id": package_id,
            "capability_matrix": matrix,
            "limit": limit,
            "offset": offset,
            "filters": filters,
            "fields": field_names,
        }
        if resource_snapshot is not None:
            ingest_kwargs["resource_dict"] = resource_snapshot
        if package_snapshot is not None:
            ingest_kwargs["package_dict"] = package_snapshot

        ingestion = self.ckan.ingest_resource(resource_id, **ingest_kwargs)
        if not fingerprint_ready:
            fallback_payload = {
                "mode": "ingestion_digest_fallback",
                "reason": "upstream fingerprint unavailable",
                "ingestion_path": ingestion.path,
            }
            fallback_payload["metadata"] = {
                "resource_id": ingestion.resource_id,
                "package_id": ingestion.package_id,
                "resource_last_modified": ingestion.resource.get("last_modified"),
                "package_metadata_modified": (ingestion.package or {}).get("metadata_modified") if ingestion.package else None,
            }
            upstream_fingerprint = hashlib.sha256(json.dumps({
                "rows": ingestion.rows,
                "resource": fallback_payload["metadata"],
            }, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            fingerprint_payload = fallback_payload
        return self._cache_ingestion_result(
            ingestion,
            upstream_fingerprint=upstream_fingerprint,
            upstream_fingerprint_payload=fingerprint_payload,
            force=force,
        )

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
        answer.evidence.setdefault("upstream_fingerprint", entry.upstream_fingerprint)
        answer.evidence.setdefault("upstream_fingerprint_mode", entry.upstream_fingerprint_payload.get("mode", self.fingerprint_mode))
        entry.last_answer = answer
        return answer

    def _cache_ingestion_result(
        self,
        ingestion: CKANIngestionResult,
        *,
        upstream_fingerprint: str | None = None,
        upstream_fingerprint_payload: dict[str, Any] | None = None,
        force: bool = False,
    ) -> DatasetCacheEntry:
        digest = hashlib.sha256(json.dumps(ingestion.rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        existing = self._cache.get(ingestion.resource_id)
        if not force and existing and existing.digest == digest:
            existing.package_id = ingestion.package_id
            existing.ingestion_path = ingestion.path
            existing.ingestion_attempts = list(ingestion.attempts)
            existing.ingestion_metadata = dict(ingestion.metadata)
            existing.resource_snapshot = dict(ingestion.resource)
            existing.package_snapshot = dict(ingestion.package) if ingestion.package else None
            existing.fields = list(ingestion.fields)
            existing.upstream_fingerprint = upstream_fingerprint
            existing.upstream_fingerprint_payload = dict(upstream_fingerprint_payload or {})
            self._persist_dataset_entry(existing)
            return existing

        verification = self.verifier.verify_source_snapshot(json.dumps(ingestion.rows, default=str))
        if not verification.passed and getattr(verification, "issue_type", "") == "syntax_error":
            raise ValueError("Dataset cache failed deterministic serialization verification.")

        entry = DatasetCacheEntry(
            resource_id=ingestion.resource_id,
            digest=digest,
            rows=list(ingestion.rows),
            fields=list(ingestion.fields),
            package_id=ingestion.package_id,
            upstream_fingerprint=upstream_fingerprint,
            upstream_fingerprint_payload=dict(upstream_fingerprint_payload or {}),
            ingestion_path=ingestion.path,
            ingestion_attempts=list(ingestion.attempts),
            ingestion_metadata=dict(ingestion.metadata),
            resource_snapshot=dict(ingestion.resource),
            package_snapshot=dict(ingestion.package) if ingestion.package else None,
        )
        self._cache[ingestion.resource_id] = entry
        self._persist_dataset_entry(entry)
        return entry

    def _dataset_entry_from_dict(self, payload: Mapping[str, Any]) -> DatasetCacheEntry:
        fields = [SchemaField(**item) for item in payload.get("fields", [])]
        attempts = [IngestionAttempt(**item) for item in payload.get("ingestion_attempts", [])]
        return DatasetCacheEntry(
            resource_id=str(payload.get("resource_id", "")),
            digest=str(payload.get("digest", "")),
            rows=[dict(row) for row in payload.get("rows", [])],
            fields=fields,
            package_id=payload.get("package_id"),
            upstream_fingerprint=payload.get("upstream_fingerprint"),
            upstream_fingerprint_payload=dict(payload.get("upstream_fingerprint_payload", {})),
            ingestion_path=str(payload.get("ingestion_path", "unknown")),
            ingestion_attempts=attempts,
            ingestion_metadata=dict(payload.get("ingestion_metadata", {})),
            resource_snapshot=dict(payload.get("resource_snapshot", {})),
            package_snapshot=dict(payload.get("package_snapshot", {})) if payload.get("package_snapshot") else None,
        )

    def _load_host_state(self) -> dict[str, Any]:
        if not self.persist_host_state or not self.state_file.exists():
            return {"resources": {}}
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {"resources": {}}

    def _load_capability_matrix_from_state(self, sample_resource_id: str | None) -> CKANCapabilityMatrix | None:
        payload = self._host_state.get("capability_matrix")
        if not isinstance(payload, Mapping):
            return None
        persisted_sample = self._host_state.get("probe_sample_resource_id")
        if sample_resource_id and persisted_sample and sample_resource_id != persisted_sample:
            return None
        try:
            return CKANCapabilityMatrix.from_dict(payload)
        except Exception:
            return None

    def _persist_dataset_entry(self, entry: DatasetCacheEntry) -> None:
        resources = self._host_state.setdefault("resources", {})
        resources[entry.resource_id] = {
            "upstream_fingerprint": entry.upstream_fingerprint,
            "ingestion_digest": entry.digest,
            "package_id": entry.package_id,
            "ingestion_path": entry.ingestion_path,
            "ingestion_metadata": dict(entry.ingestion_metadata),
            "cache_entry": entry.to_dict(),
        }
        self._save_host_state()

    def _save_host_state(self) -> None:
        if not self.persist_host_state:
            return
        self.state_file.write_text(json.dumps(self._host_state, indent=2, sort_keys=True, default=str))
