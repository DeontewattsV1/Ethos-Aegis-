from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from ethos_aegis.agent.scaffolds.task_verifier_mesh import DeterministicVerifier

from .ckan_adapter import CKANCapabilityMatrix, CKANClient, CKANIngestionResult, SchemaField
from .question_answering import AnswerRecord, VeriflowReasoner


@dataclass(slots=True)
class DatasetCacheEntry:
    resource_id: str
    digest: str
    rows: list[dict[str, Any]]
    fields: list[SchemaField]
    # Ingestion metadata surfaced to answer_question evidence
    package_id: str = ""
    ingestion_path: str = ""
    ingestion_metadata: dict[str, Any] = field(default_factory=dict)
    upstream_fingerprint: str = ""
    last_answer: Optional[AnswerRecord] = None


class VeriflowImmuneSystem:
    """
    Agentic data immune system for CKAN-backed knowledge hubs.

    Flow:
        CKAN resource -> startup capability probe -> digest/fingerprint check
        -> deterministic verifier -> formula cache -> answer engine

    Args:
        ckan:                  CKANClient instance.
        verifier:              DeterministicVerifier (auto-created if None).
        reasoner:              VeriflowReasoner (auto-created if None).
        probe_on_startup:      Run capability probe at construction time.
        sample_resource_id:    Resource to probe on startup.
        state_dir:             Optional path for persisting cache state.
        fingerprint_mode:      ``"digest"`` (default) or
                               ``"datastore_lightweight"`` -- lightweight mode
                               re-ingests when row content changes even if
                               CKAN metadata timestamps are unchanged.
        row_signature_limit:   How many rows to include in lightweight
                               fingerprint (default: 100).
    """

    def __init__(
        self,
        ckan: CKANClient,
        verifier: DeterministicVerifier | None = None,
        reasoner: VeriflowReasoner | None = None,
        *,
        probe_on_startup: bool = True,
        sample_resource_id: str | None = None,
        state_dir: Path | str | None = None,
        fingerprint_mode: str = "digest",
        row_signature_limit: int = 100,
    ) -> None:
        self.ckan = ckan
        self.verifier = verifier or DeterministicVerifier()
        self.reasoner = reasoner or VeriflowReasoner()
        self._cache: dict[str, DatasetCacheEntry] = {}
        self._capability_matrix: CKANCapabilityMatrix | None = None
        self._probe_sample_resource_id = sample_resource_id
        self._state_dir = Path(state_dir) if state_dir else None
        self._fingerprint_mode = fingerprint_mode
        self._row_signature_limit = row_signature_limit
        if probe_on_startup:
            self.bootstrap(sample_resource_id=sample_resource_id)

    # -- Public read-only access to the cache --------------------------------

    @property
    def cache(self) -> dict[str, DatasetCacheEntry]:
        return self._cache

    @property
    def capability_matrix(self) -> CKANCapabilityMatrix | None:
        return self._capability_matrix

    # -- Bootstrap -----------------------------------------------------------

    def bootstrap(
        self,
        *,
        sample_resource_id: str | None = None,
        force: bool = False,
    ) -> CKANCapabilityMatrix:
        sample = sample_resource_id or self._probe_sample_resource_id
        if self._capability_matrix is not None and not force:
            if sample and sample != self._probe_sample_resource_id:
                force = True
            else:
                return self._capability_matrix
        matrix = self.ckan.probe_capabilities(sample_resource_id=sample)
        self._capability_matrix = matrix
        self._probe_sample_resource_id = sample
        return matrix

    # -- Core ingestion ------------------------------------------------------

    def refresh_resource(self, resource_id: str) -> DatasetCacheEntry:
        """Ingest (or re-ingest if stale) a CKAN resource into the cache.

        Automatically bootstraps the capability matrix if not yet done.
        In ``datastore_lightweight`` fingerprint mode, performs a cheap row
        probe via ``datastore_search`` *before* calling ``ingest_resource`` so
        that unchanged resources skip the full ingestion round-trip entirely.

        Args:
            resource_id: CKAN resource UUID to ingest.

        Returns:
            The (possibly updated) ``DatasetCacheEntry`` for this resource.
        """
        # Ensure capability matrix is available
        if self._capability_matrix is None:
            self.bootstrap(sample_resource_id=resource_id)

        existing = self._cache.get(resource_id)

        # Lightweight mode: cheap probe BEFORE full ingest
        if self._fingerprint_mode == "datastore_lightweight" and existing is not None:
            probe_fingerprint = self._probe_lightweight_fingerprint(resource_id)
            if probe_fingerprint == existing.upstream_fingerprint:
                return existing

        # Full ingest
        result: CKANIngestionResult = self.ckan.ingest_resource(resource_id)
        rows   = result.rows
        fields = result.fields

        # Compute fingerprint and digest
        fingerprint = self._compute_fingerprint(resource_id, rows)
        digest = hashlib.sha256(
            json.dumps(rows, sort_keys=True).encode("utf-8")
        ).hexdigest()

        # Standard digest mode: skip storing if unchanged
        if (
            self._fingerprint_mode == "digest"
            and existing is not None
            and existing.digest == digest
        ):
            return existing

        # Run deterministic verification
        verification = self.verifier.verify_source_snapshot(json.dumps(rows))
        if not verification.passed and getattr(verification, "issue_type", "") == "syntax_error":
            raise ValueError(
                "Dataset cache failed deterministic serialization verification."
            )

        ingestion_path = result.path if hasattr(result, "path") else ""
        package_id     = result.package_id if hasattr(result, "package_id") else ""
        metadata       = result.metadata if hasattr(result, "metadata") else {}

        entry = DatasetCacheEntry(
            resource_id=resource_id,
            digest=digest,
            rows=rows,
            fields=fields,
            package_id=package_id,
            ingestion_path=ingestion_path,
            ingestion_metadata=metadata,
            upstream_fingerprint=fingerprint,
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
        """Answer a question about a cached resource.

        Auto-refreshes the resource if it is not yet in cache.
        """
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
        # Enrich evidence with ingestion context
        answer.evidence.update({
            "ingestion_path":     entry.ingestion_path,
            "ingestion_metadata": entry.ingestion_metadata,
        })
        entry.last_answer = answer
        return answer

    # -- Internal helpers ----------------------------------------------------

    def _probe_lightweight_fingerprint(self, resource_id: str) -> str:
        """Fetch a small row sample via datastore_search to cheaply detect changes."""
        try:
            result = self.ckan.datastore_search(
                resource_id, limit=self._row_signature_limit
            )
            rows = result.get("result", {}).get("records", [])
        except Exception:
            # If probe fails (e.g. datastore unavailable), fall back to full ingest
            return ""
        raw = json.dumps(rows[: self._row_signature_limit], sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _compute_fingerprint(
        self, resource_id: str, rows: list[dict[str, Any]]
    ) -> str:
        if self._fingerprint_mode == "datastore_lightweight":
            sample = rows[: self._row_signature_limit]
            raw = json.dumps(sample, sort_keys=True).encode("utf-8")
        else:
            raw = json.dumps(rows, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
