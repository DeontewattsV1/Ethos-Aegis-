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

    @property
    def state_file(self) -> Optional[Path]:
        """Path to the persisted state JSON, or None if no state_dir is configured."""
        if self._state_dir is None:
            return None
        return self._state_dir / "veriflow_immune_state.json"

    # -- Bootstrap -----------------------------------------------------------

    def bootstrap(
        self,
        *,
        sample_resource_id: str | None = None,
        force: bool = False,
    ) -> CKANCapabilityMatrix:
        sample = sample_resource_id or self._probe_sample_resource_id

        # Try loading persisted matrix before probing the network
        if not force and self._capability_matrix is None:
            loaded = self._load_state()
            if loaded is not None:
                self._capability_matrix = loaded
                self._probe_sample_resource_id = sample
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

    def _persist_state(self) -> None:
        """Persist capability matrix to state_file if state_dir is configured."""
        if self._state_dir is None or self._capability_matrix is None:
            return
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            sf = self.state_file
            caps = {
                k: {"name": v.name, "state": v.state, "source": v.source, "detail": v.detail}
                for k, v in self._capability_matrix.capabilities.items()
            }
            import json as _json
            sf.write_text(_json.dumps({
                "api_base": self._capability_matrix.api_base,
                "version": self._capability_matrix.version.raw,
                "capabilities": caps,
            }, indent=2))
        except Exception:
            pass

    def _load_state(self) -> "CKANCapabilityMatrix | None":
        """Load persisted capability matrix from state_file, or return None."""
        sf = self.state_file
        if sf is None or not sf.exists():
            return None
        try:
            import json as _json
            from .ckan_adapter import CKANVersion, CapabilityRecord
            data = _json.loads(sf.read_text())
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

    # -- Core ingestion ------------------------------------------------------

    def refresh_resource(self, resource_id: str) -> DatasetCacheEntry:
        """Ingest (or re-ingest if stale) a CKAN resource into the cache.

        Always performs a cheap upstream fingerprint probe first so that
        unchanged resources skip the full ingestion round-trip entirely.

        - Default mode (``"digest"``): fingerprint = SHA-256 of resource +
          package metadata timestamps via ``resource_show`` / ``package_show``.
        - ``"datastore_lightweight"``: fingerprint = SHA-256 of a small row
          sample via ``datastore_search``.

        Args:
            resource_id: CKAN resource UUID to ingest.

        Returns:
            The (possibly updated) ``DatasetCacheEntry`` for this resource.
        """
        # Ensure capability matrix is available
        if self._capability_matrix is None:
            self.bootstrap(sample_resource_id=resource_id)

        existing = self._cache.get(resource_id)

        # Always probe upstream fingerprint first (cheap metadata or row sample)
        if existing is not None:
            probe_fingerprint = self._probe_upstream_fingerprint(resource_id)
            if probe_fingerprint and probe_fingerprint == existing.upstream_fingerprint:
                return existing

        # Full ingest
        result: CKANIngestionResult = self.ckan.ingest_resource(resource_id)
        rows   = result.rows
        fields = result.fields

        # Compute fingerprint and digest
        fingerprint = self._probe_upstream_fingerprint(resource_id) or self._compute_fingerprint(resource_id, rows)
        digest = hashlib.sha256(
            json.dumps(rows, sort_keys=True).encode("utf-8")
        ).hexdigest()

        # Extra guard: if fingerprint AND digest both match, return cached
        if (
            existing is not None
            and existing.digest == digest
            and existing.upstream_fingerprint == fingerprint
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

    def _probe_upstream_fingerprint(self, resource_id: str) -> str:
        """Compute a cheap upstream fingerprint without a full ingest.

        - ``datastore_lightweight`` mode: hash a small row sample via
          ``datastore_search`` so that row changes (even without metadata
          changes) are detected.
        - Default ``digest`` mode: hash resource + package metadata timestamps
          via ``resource_show`` / ``package_show`` for a network-cheap probe.
        Returns ``""`` on any error (caller falls through to full ingest).
        """
        try:
            if self._fingerprint_mode == "datastore_lightweight":
                result = self.ckan.datastore_search(
                    resource_id, limit=self._row_signature_limit or 100
                )
                rows = result.get("result", {}).get("records", [])
                limit = self._row_signature_limit or len(rows)
                raw = json.dumps(rows[:limit], sort_keys=True).encode("utf-8")
                return hashlib.sha256(raw).hexdigest()
            else:
                resource = self.ckan.resource_show(resource_id).get("result", {})
                package_id = resource.get("package_id", "")
                package: dict = {}
                if package_id:
                    try:
                        package = self.ckan.package_show(package_id).get("result", {})
                    except Exception:
                        pass
                parts = [
                    resource.get("last_modified", ""),
                    resource.get("metadata_modified", ""),
                    package.get("metadata_modified", ""),
                ]
                return hashlib.sha256("|".join(parts).encode()).hexdigest()
        except Exception:
            return ""

    def _compute_fingerprint(
        self, resource_id: str, rows: list[dict[str, Any]]
    ) -> str:
        if self._fingerprint_mode == "datastore_lightweight":
            sample = rows[: self._row_signature_limit] if self._row_signature_limit else rows
            raw = json.dumps(sample, sort_keys=True).encode("utf-8")
        else:
            raw = json.dumps(rows, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
