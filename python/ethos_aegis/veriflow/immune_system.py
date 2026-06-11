"""
VeriflowImmuneSystem -- agentic data immune system for CKAN-backed knowledge hubs.

Flow:
    CKAN resource -> startup capability probe -> digest/fingerprint check
    -> deterministic verifier -> formula cache -> answer engine
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
    last_answer: Optional[AnswerRecord] = None

    @classmethod
    def from_ingestion(
        cls,
        result: CKANIngestionResult,
        *,
        upstream_fingerprint: str = "",
    ) -> "DatasetCacheEntry":
        return cls(
            resource_id=result.resource_id,
            package_id=result.package_id,
            rows=result.rows,
            fields=result.fields,
            ingestion_path=result.path,
            ingestion_metadata=result.metadata or {},
            upstream_fingerprint=upstream_fingerprint,
        )


def _row_digest(rows: list[dict[str, Any]]) -> str:
    """SHA-256 digest of the canonical JSON serialisation of *rows*."""
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _metadata_fingerprint(resource: dict[str, Any], package: dict[str, Any]) -> str:
    """Lightweight fingerprint based on last-modified timestamps."""
    parts = [
        resource.get("last_modified", ""),
        resource.get("metadata_modified", ""),
        package.get("metadata_modified", ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class VeriflowImmuneSystem:
    """
    Agentic data immune system for CKAN-backed knowledge hubs.

    Args:
        ckan:               CKANClient instance (or subclass / mock).
        verifier:           DeterministicVerifier. Defaults to a fresh instance.
        reasoner:           VeriflowReasoner. Defaults to a fresh instance.
        probe_on_startup:   Run capability probe during ``__init__``. Default True.
        sample_resource_id: Resource ID to use for the startup probe.
        state_dir:          Optional Path for on-disk fingerprint persistence.
        fingerprint_mode:   ``"digest"`` (full SHA-256 of rows, default) or
                            ``"datastore_lightweight"`` (metadata timestamp only).
        row_signature_limit: Max rows considered when computing digest. 0 = all.
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

    # -- Public properties ---------------------------------------------------

    @property
    def capability_matrix(self) -> CKANCapabilityMatrix | None:
        return self._capability_matrix

    @property
    def cache(self) -> dict[str, DatasetCacheEntry]:
        """Read-only view of the resource cache."""
        return self._cache

    # -- Lifecycle -----------------------------------------------------------

    def bootstrap(
        self,
        *,
        sample_resource_id: str | None = None,
        force: bool = False,
    ) -> CKANCapabilityMatrix:
        """Probe CKAN capabilities and populate ``capability_matrix``."""
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

    # -- Core refresh --------------------------------------------------------

    def refresh_resource(self, resource_id: str) -> DatasetCacheEntry:
        """
        Ingest or re-use a cached CKAN resource.

        Steps:
        1. Ensure capability matrix is populated (probe if needed).
        2. Ingest the resource via the CKAN adapter.
        3. Compute the upstream fingerprint according to *fingerprint_mode*.
        4. Return cached entry if fingerprint unchanged; otherwise verify +
           cache the new ingestion.

        Args:
            resource_id: CKAN resource UUID.

        Returns:
            A ``DatasetCacheEntry`` with rows, fields, path, and metadata.
        """
        # Ensure we have a capability matrix
        if self._capability_matrix is None:
            self.bootstrap(sample_resource_id=resource_id)

        # Compute upstream fingerprint without ingesting if lightweight mode
        if self._fingerprint_mode == "datastore_lightweight":
            new_fingerprint = self._lightweight_fingerprint(resource_id)
            existing = self._cache.get(resource_id)
            if existing and existing.upstream_fingerprint == new_fingerprint:
                return existing

        # Ingest the resource
        result: CKANIngestionResult = self.ckan.ingest_resource(resource_id)

        # Compute fingerprint for full-digest mode
        rows_sample = (
            result.rows[: self._row_signature_limit]
            if self._row_signature_limit > 0
            else result.rows
        )
        if self._fingerprint_mode == "datastore_lightweight":
            fingerprint = new_fingerprint  # already computed above
        else:
            fingerprint = _row_digest(rows_sample)

        # Check digest cache (avoid re-verifying identical data)
        existing = self._cache.get(resource_id)
        if existing and existing.upstream_fingerprint == fingerprint:
            return existing

        # Run deterministic verifier
        payload = json.dumps(rows_sample, sort_keys=True, default=str)
        verification = self.verifier.verify_source_snapshot(payload)
        if not verification.passed and getattr(verification, "issue_type", "") == "syntax_error":
            raise ValueError(
                "Dataset cache failed deterministic serialization verification."
            )

        entry = DatasetCacheEntry.from_ingestion(result, upstream_fingerprint=fingerprint)
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
        """
        Answer a natural-language question about a cached resource.

        Auto-refreshes the resource if it is not yet in cache.
        Enriches the answer evidence with ingestion context.
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
        # Enrich evidence with ingestion provenance
        answer.evidence["ingestion_path"] = entry.ingestion_path
        answer.evidence["ingestion_metadata"] = entry.ingestion_metadata
        entry.last_answer = answer
        return answer

    # -- Helpers -------------------------------------------------------------

    def _lightweight_fingerprint(self, resource_id: str) -> str:
        """Compute a metadata-only fingerprint without fetching rows."""
        try:
            resource = self.ckan.resource_show(resource_id).get("result", {})
            package_id = resource.get("package_id", "")
            package = {}
            if package_id:
                try:
                    package = self.ckan.package_show(package_id).get("result", {})
                except Exception:
                    pass
            return _metadata_fingerprint(resource, package)
        except Exception:
            return ""
