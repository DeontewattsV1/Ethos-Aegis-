"""
VeriflowImmuneSystem -- agentic data immune system for CKAN-backed knowledge hubs.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ethos_aegis.agent.scaffolds.task_verifier_mesh import DeterministicVerifier

from .ckan_adapter import CKANCapabilityMatrix, CKANClient, CKANIngestionResult, SchemaField
from .question_answering import AnswerRecord, VeriflowReasoner


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DatasetCacheEntry:
    """Cached result of a CKAN resource ingestion pass."""

    resource_id: str
    package_id: str
    rows: list[dict[str, Any]]
    fields: list[SchemaField]
    ingestion_path: str
    ingestion_metadata: dict[str, Any]
    upstream_fingerprint: str = ""
    digest: str = ""
    last_answer: Optional[AnswerRecord] = None

    @classmethod
    def from_ingestion(
        cls,
        result: CKANIngestionResult,
        *,
        upstream_fingerprint: str = "",
        digest: str = "",
    ) -> "DatasetCacheEntry":
        return cls(
            resource_id=result.resource_id,
            package_id=result.package_id,
            rows=result.rows,
            fields=result.fields,
            ingestion_path=result.path,
            ingestion_metadata=result.metadata or {},
            upstream_fingerprint=upstream_fingerprint,
            digest=digest,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_digest(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _metadata_fingerprint(resource: dict[str, Any], package: dict[str, Any]) -> str:
    parts = [
        resource.get("last_modified", ""),
        resource.get("metadata_modified", ""),
        package.get("metadata_modified", ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


_STATE_FILE_NAME = "veriflow_immune_state.json"


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class VeriflowImmuneSystem:
    """
    Agentic data immune system for CKAN-backed knowledge hubs.

    Args:
        ckan:                CKANClient instance.
        verifier:            DeterministicVerifier (default: fresh instance).
        reasoner:            VeriflowReasoner (default: fresh instance).
        probe_on_startup:    Run capability probe during ``__init__``.
        sample_resource_id:  Resource ID used for the startup probe.
        state_dir:           Optional Path; persists capability matrix JSON.
        fingerprint_mode:    ``"digest"`` (full SHA-256, default) or
                             ``"datastore_lightweight"`` (metadata timestamps).
        row_signature_limit: Max rows used when computing digest. 0 = all.
    """

    def __init__(
        self,
        ckan: CKANClient,
        verifier: DeterministicVerifier | None = None,
        reasoner: VeriflowReasoner | None = None,
        *,
        probe_on_startup: bool = True,
        sample_resource_id: str | None = None,
        state_dir: Path | None = None,
        fingerprint_mode: str = "digest",
        row_signature_limit: int = 0,
    ) -> None:
        self.ckan = ckan
        self.verifier = verifier or DeterministicVerifier()
        self.reasoner = reasoner or VeriflowReasoner()
        self._cache: dict[str, DatasetCacheEntry] = {}
        self._capability_matrix: CKANCapabilityMatrix | None = None
        self._probe_sample_resource_id = sample_resource_id
        self._state_dir = state_dir
        self._fingerprint_mode = fingerprint_mode
        self._row_signature_limit = row_signature_limit

        if probe_on_startup:
            self.bootstrap(sample_resource_id=sample_resource_id)

    # -- Properties ----------------------------------------------------------

    @property
    def capability_matrix(self) -> CKANCapabilityMatrix | None:
        return self._capability_matrix

    @property
    def cache(self) -> dict[str, DatasetCacheEntry]:
        return self._cache

    @property
    def state_file(self) -> Optional[Path]:
        """Path to the persisted state JSON, or None if no state_dir set."""
        if self._state_dir is None:
            return None
        return self._state_dir / _STATE_FILE_NAME

    # -- Lifecycle -----------------------------------------------------------

    def bootstrap(
        self,
        *,
        sample_resource_id: str | None = None,
        force: bool = False,
    ) -> CKANCapabilityMatrix:
        sample = sample_resource_id or self._probe_sample_resource_id

        # Try loading from persisted state first
        if not force and self._capability_matrix is None and self._state_dir:
            loaded = self._load_state()
            if loaded is not None:
                self._capability_matrix = loaded
                return loaded

        if self._capability_matrix is not None and not force:
            if sample and sample != self._probe_sample_resource_id:
                force = True
            else:
                return self._capability_matrix

        matrix = self.ckan.probe_capabilities(sample_resource_id=sample)
        self._capability_matrix = matrix
        self._probe_sample_resource_id = sample
        self._persist_state()
        return matrix

    # -- Refresh -------------------------------------------------------------

    def refresh_resource(self, resource_id: str) -> DatasetCacheEntry:
        """Ingest or re-use a cached CKAN resource.

        Args:
            resource_id: CKAN resource UUID.
        Returns:
            DatasetCacheEntry with rows, fields, path, metadata, fingerprint.
        """
        if self._capability_matrix is None:
            self.bootstrap(sample_resource_id=resource_id)

        # Lightweight mode: check metadata fingerprint before fetching rows
        if self._fingerprint_mode == "datastore_lightweight":
            new_fp = self._lightweight_fingerprint(resource_id)
            existing = self._cache.get(resource_id)
            if existing and existing.upstream_fingerprint == new_fp:
                return existing

        # Ingest
        result: CKANIngestionResult = self.ckan.ingest_resource(resource_id)

        rows_sample = (
            result.rows[: self._row_signature_limit]
            if self._row_signature_limit > 0
            else result.rows
        )

        if self._fingerprint_mode == "datastore_lightweight":
            fingerprint = new_fp  # already computed
            digest = _row_digest(rows_sample)
        else:
            digest = _row_digest(rows_sample)
            fingerprint = digest

        existing = self._cache.get(resource_id)
        if existing and existing.upstream_fingerprint == fingerprint:
            return existing

        payload = json.dumps(rows_sample, sort_keys=True, default=str)
        verification = self.verifier.verify_source_snapshot(payload)
        if not verification.passed and getattr(verification, "issue_type", "") == "syntax_error":
            raise ValueError("Dataset failed deterministic serialization verification.")

        entry = DatasetCacheEntry.from_ingestion(
            result, upstream_fingerprint=fingerprint, digest=digest
        )
        self._cache[resource_id] = entry
        return entry

    # -- Question answering --------------------------------------------------

    def answer_question(
        self,
        resource_id: str,
        question: str,
        *,
        target_field: str | None = None,
    ) -> AnswerRecord:
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
        answer.evidence["ingestion_path"] = entry.ingestion_path
        answer.evidence["ingestion_metadata"] = entry.ingestion_metadata
        entry.last_answer = answer
        return answer

    # -- Persistence helpers -------------------------------------------------

    def _persist_state(self) -> None:
        if self._state_dir is None or self._capability_matrix is None:
            return
        self._state_dir.mkdir(parents=True, exist_ok=True)
        sf = self.state_file
        try:
            data = {
                "api_base": self._capability_matrix.api_base,
                "version": self._capability_matrix.version.raw,
                "capabilities": {
                    k: {"name": v.name, "state": v.state, "source": v.source, "detail": v.detail}
                    for k, v in self._capability_matrix.capabilities.items()
                },
            }
            sf.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _load_state(self) -> Optional[CKANCapabilityMatrix]:
        sf = self.state_file
        if sf is None or not sf.exists():
            return None
        try:
            from .ckan_adapter import CKANVersion, CapabilityRecord
            data = json.loads(sf.read_text())
            caps = {
                k: CapabilityRecord(
                    name=v["name"], state=v["state"],
                    source=v["source"], detail=v["detail"],
                )
                for k, v in data.get("capabilities", {}).items()
            }
            return CKANCapabilityMatrix(
                api_base=data["api_base"],
                version=CKANVersion.parse(data["version"]),
                capabilities=caps,
            )
        except Exception:
            return None

    def _lightweight_fingerprint(self, resource_id: str) -> str:
        try:
            resource = self.ckan.resource_show(resource_id).get("result", {})
            package_id = resource.get("package_id", "")
            package: dict = {}
            if package_id:
                try:
                    package = self.ckan.package_show(package_id).get("result", {})
                except Exception:
                    pass
            return _metadata_fingerprint(resource, package)
        except Exception:
            return ""
