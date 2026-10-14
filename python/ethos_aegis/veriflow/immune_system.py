from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ethos_aegis.agent.scaffolds.task_verifier_mesh import DeterministicVerifier
from ethos_aegis.mythos_runtime.authority import ExecutionGrant
from ethos_aegis.mythos_runtime.assurance import StateIntegrityError
from ethos_aegis.mythos_runtime.veriflow_runtime import MythosVeriflowRuntime

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
        fingerprint_mode:      ``"auto"`` (default) selects a lightweight row
                               signature when CKAN Datastore is available and
                               otherwise uses metadata fingerprints.
        mythos_runtime:        Optional production assurance bridge. When set,
                               probe/refresh/answer execution is grant-gated,
                               state is authenticated, and evidence is retained.
        execution_grant:       Short-lived operator-issued grant consumed by the
                               configured Mythos/VeriFlow runtime.
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
        fingerprint_mode: str = "auto",
        row_signature_limit: int = 100,
        mythos_runtime: MythosVeriflowRuntime | None = None,
        execution_grant: str | None = None,
    ) -> None:
        self.ckan = ckan
        self.verifier = verifier or DeterministicVerifier()
        self.reasoner = reasoner or VeriflowReasoner()
        self._cache: dict[str, DatasetCacheEntry] = {}
        self._capability_matrix: CKANCapabilityMatrix | None = None
        self._probe_sample_resource_id = sample_resource_id
        self._mythos_runtime = mythos_runtime
        self._execution_grant = execution_grant
        if mythos_runtime is not None and mythos_runtime.environment.ckan_base_url != self.ckan.base_url:
            raise ValueError("Mythos trusted CKAN host must match the VeriFlow CKAN client")
        if state_dir is not None:
            self._state_dir = Path(state_dir)
        elif mythos_runtime is not None:
            self._state_dir = mythos_runtime.state_dir / "veriflow-state"
        else:
            self._state_dir = None
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
    def mythos_runtime(self) -> MythosVeriflowRuntime | None:
        return self._mythos_runtime

    def set_execution_grant(self, token: str | None) -> None:
        """Rotate the short-lived execution grant supplied by the trusted host."""
        self._execution_grant = token

    def _authorize_mythos(self, action: str, resource_id: str, purpose: str) -> ExecutionGrant | None:
        if self._mythos_runtime is None:
            return None
        return self._mythos_runtime.authorize(
            self._execution_grant,
            action=action,
            resource_id=resource_id,
            purpose=purpose,
        )

    def _record_mythos(
        self,
        grant: ExecutionGrant | None,
        *,
        event_type: str,
        action: str,
        resource_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if self._mythos_runtime is None or grant is None:
            return
        self._mythos_runtime.record(
            event_type=event_type,
            action=action,
            resource_id=resource_id,
            subject=grant.subject,
            metadata=metadata,
        )

    @property
    def state_file(self) -> Optional[Path]:
        """Path to the persisted state JSON, or None if no state_dir is configured."""
        if self._state_dir is None:
            return None
        return self._state_dir / "veriflow_immune_state.json"

    def _empty_state(self) -> dict[str, Any]:
        return {"schema_version": 2, "host": self.ckan.base_url, "resources": {}}

    def _legacy_payload_matches_host(self, payload: Mapping[str, Any]) -> bool:
        host = payload.get("host")
        if host is not None:
            return str(host).rstrip("/") == self.ckan.base_url

        matrix = payload.get("capability_matrix")
        if isinstance(matrix, Mapping):
            api_base = matrix.get("api_base")
        else:
            api_base = payload.get("api_base")
        if not api_base:
            return False

        expected = f"{self.ckan.base_url}/api/3/action"
        return str(api_base).rstrip("/") == expected.rstrip("/")

    def _prune_resource_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._mythos_runtime is None:
            return payload
        resources = payload.get("resources")
        if not isinstance(resources, Mapping):
            payload["resources"] = {}
            return payload

        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=self._mythos_runtime.retention.resource_state_ttl_seconds
        )
        retained: list[tuple[str, Mapping[str, Any], datetime]] = []
        for resource_id, raw in resources.items():
            if not isinstance(raw, Mapping):
                continue
            saved_at = raw.get("saved_at")
            if not isinstance(saved_at, str):
                continue
            try:
                saved = datetime.fromisoformat(saved_at.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            if saved >= cutoff:
                retained.append((str(resource_id), raw, saved))

        retained.sort(key=lambda item: item[2], reverse=True)
        payload["resources"] = {
            resource_id: dict(raw)
            for resource_id, raw, _ in retained[: self._mythos_runtime.retention.max_resources]
        }
        return payload

    def _load_host_state(self) -> dict[str, Any]:
        if self._state_dir is None:
            return self._empty_state()

        candidates = [self.state_file, self._legacy_state_file]
        for path in candidates:
            if path is None or not path.exists():
                continue
            if self._mythos_runtime is not None:
                if path.is_symlink() or path.parent.is_symlink():
                    raise StateIntegrityError("VeriFlow state symlinks are forbidden in production mode")
                if path.stat().st_size > self._mythos_runtime.retention.max_state_bytes:
                    raise StateIntegrityError("VeriFlow state exceeds configured size limit")
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                if self._mythos_runtime is not None:
                    raise StateIntegrityError("VeriFlow production state is unreadable") from exc
                continue
            if not isinstance(loaded, dict):
                if self._mythos_runtime is not None:
                    raise StateIntegrityError("VeriFlow production state schema is invalid")
                continue

            if self._mythos_runtime is not None:
                payload = self._mythos_runtime.unprotect_state(loaded)
            else:
                payload = loaded

            is_legacy = path == self._legacy_state_file
            if is_legacy and not self._legacy_payload_matches_host(payload):
                if self._mythos_runtime is not None:
                    raise StateIntegrityError("legacy state does not match the trusted CKAN host")
                continue

            if "capability_matrix" not in payload and "api_base" in payload and "capabilities" in payload:
                payload = {
                    "schema_version": 2,
                    "host": self.ckan.base_url,
                    "resources": {},
                    "capability_matrix": payload,
                }

            host = payload.get("host")
            if host is not None and str(host).rstrip("/") != self.ckan.base_url:
                if self._mythos_runtime is not None:
                    raise StateIntegrityError("persisted state belongs to another CKAN host")
                continue
            payload.setdefault("schema_version", 2)
            payload.setdefault("host", self.ckan.base_url)
            payload.setdefault("resources", {})
            return self._prune_resource_state(payload)

        return self._empty_state()

    def _save_host_state(self) -> None:
        path = self.state_file
        if path is None or self._state_dir is None:
            return
        if self._state_dir.is_symlink():
            raise StateIntegrityError("VeriFlow state directory symlink is forbidden")
        self._state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            self._state_dir.chmod(0o700)
        if path.is_symlink() or path.parent.is_symlink():
            raise StateIntegrityError("VeriFlow state file symlink is forbidden")

        self._state = self._prune_resource_state(self._state)
        stored: Mapping[str, Any]
        if self._mythos_runtime is not None:
            stored = self._mythos_runtime.protect_state(self._state)
        else:
            stored = self._state
        payload = json.dumps(stored, indent=2, sort_keys=True, default=str).encode("utf-8") + b"\n"
        if self._mythos_runtime is not None and len(payload) > self._mythos_runtime.retention.max_state_bytes:
            raise StateIntegrityError("VeriFlow state would exceed configured size limit")

        lock = self._mythos_runtime.state_write_lock(path) if self._mythos_runtime is not None else None
        temporary: Path | None = None

        def write_state() -> None:
            nonlocal temporary
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                if os.name == "posix":
                    os.fchmod(handle.fileno(), 0o600)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
            if os.name == "posix":
                path.chmod(0o600)

        try:
            if lock is None:
                write_state()
            else:
                with lock:
                    write_state()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _matrix_from_dict(self, payload: Mapping[str, Any]) -> CKANCapabilityMatrix:
        version_payload = payload.get("version")
        if isinstance(version_payload, Mapping):
            version = CKANVersion(
                raw=str(version_payload.get("raw") or "unknown"),
                major=version_payload.get("major"),
                minor=version_payload.get("minor"),
                patch=version_payload.get("patch"),
                prerelease=version_payload.get("prerelease"),
            )
        else:
            version = CKANVersion.parse(str(version_payload or "unknown"))

        capabilities: dict[str, CapabilityRecord] = {}
        for name, raw_record in (payload.get("capabilities") or {}).items():
            if not isinstance(raw_record, Mapping):
                continue
            evidence = [
                ProbeEvidence(
                    name=str(item.get("name") or ""),
                    ok=bool(item.get("ok")),
                    source=str(item.get("source") or ""),
                    detail=str(item.get("detail") or ""),
                    status_code=item.get("status_code"),
                    payload=(
                        dict(item.get("payload"))
                        if isinstance(item.get("payload"), Mapping)
                        else None
                    ),
                )
                for item in (raw_record.get("evidence") or [])
                if isinstance(item, Mapping)
            ]
            capabilities[str(name)] = CapabilityRecord(
                name=str(raw_record.get("name") or name),
                state=str(raw_record.get("state") or "unavailable"),
                source=str(raw_record.get("source") or "state_cache"),
                detail=str(raw_record.get("detail") or ""),
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
        if self._state_dir is None:
            return
        self._state["host"] = self.ckan.base_url
        self._state["capability_matrix"] = matrix.to_dict()
        self._state["probe_sample_resource_id"] = self._probe_sample_resource_id
        self._save_host_state()

    def _dataset_entry_from_dict(self, payload: Mapping[str, Any]) -> DatasetCacheEntry:
        fields = [
            SchemaField(
                name=str(item.get("name") or ""),
                label=item.get("label"),
                description=item.get("description"),
                aliases=list(item.get("aliases") or []),
                unit=item.get("unit"),
                field_type=item.get("field_type"),
            )
            for item in (payload.get("fields") or [])
            if isinstance(item, Mapping)
        ]
        attempts = [
            IngestionAttempt(
                path=str(item.get("path") or ""),
                ok=bool(item.get("ok")),
                detail=str(item.get("detail") or ""),
            )
            for item in (payload.get("ingestion_attempts") or [])
            if isinstance(item, Mapping)
        ]
        return DatasetCacheEntry(
            resource_id=str(payload.get("resource_id") or ""),
            digest=str(payload.get("digest") or ""),
            rows=[dict(row) for row in (payload.get("rows") or []) if isinstance(row, Mapping)],
            fields=fields,
            package_id=payload.get("package_id"),
            ingestion_path=str(payload.get("ingestion_path") or "unknown"),
            ingestion_attempts=attempts,
            ingestion_metadata=dict(payload.get("ingestion_metadata") or {}),
            resource_snapshot=dict(payload.get("resource_snapshot") or {}),
            package_snapshot=dict(payload.get("package_snapshot")) if isinstance(payload.get("package_snapshot"), Mapping) else None,
            upstream_fingerprint=payload.get("upstream_fingerprint"),
            upstream_fingerprint_payload=dict(payload.get("upstream_fingerprint_payload") or {}),
        )

    @staticmethod
    def _rows_digest(rows: list[dict[str, Any]]) -> str:
        return hashlib.sha256(
            json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    def _restore_persisted_entry(
        self,
        resource_id: str,
        persisted: Mapping[str, Any],
        upstream_fingerprint: str,
    ) -> DatasetCacheEntry | None:
        cache_payload = persisted.get("cache_entry")
        if not isinstance(cache_payload, Mapping):
            return None
        if cache_payload.get("rows_persisted") is False:
            return None

        try:
            entry = self._dataset_entry_from_dict(cache_payload)
        except (TypeError, ValueError, KeyError):
            return None

        if entry.resource_id != resource_id:
            return None
        if entry.upstream_fingerprint != upstream_fingerprint:
            return None

        recomputed_digest = self._rows_digest(entry.rows)
        if not entry.digest or entry.digest != recomputed_digest:
            return None
        persisted_digest = persisted.get("ingestion_digest")
        if persisted_digest is not None and str(persisted_digest) != entry.digest:
            return None

        try:
            verification = self.verifier.verify_source_snapshot(
                json.dumps(entry.rows, sort_keys=True, default=str)
            )
        except Exception:
            return None
        if not verification.passed and getattr(verification, "issue_type", "") == "syntax_error":
            return None
        return entry

    def _persist_dataset_entry(self, entry: DatasetCacheEntry) -> None:
        if self._state_dir is None:
            return
        resources = self._state.setdefault("resources", {})
        cache_entry = entry.to_dict()
        persist_rows = self._mythos_runtime is None or self._mythos_runtime.retention.persist_rows
        cache_entry["rows_persisted"] = persist_rows
        cache_entry["row_count"] = len(entry.rows)
        if not persist_rows:
            cache_entry["rows"] = []
        resources[entry.resource_id] = {
            "upstream_fingerprint": entry.upstream_fingerprint,
            "ingestion_digest": entry.digest,
            "package_id": entry.package_id,
            "ingestion_path": entry.ingestion_path,
            "ingestion_metadata": dict(entry.ingestion_metadata),
            "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cache_entry": cache_entry,
        }
        self._save_host_state()

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

        if self._capability_matrix is None and not force and self._state_dir is not None:
            payload = self._state.get("capability_matrix")
            persisted_sample = self._state.get("probe_sample_resource_id")
            if isinstance(payload, Mapping) and (sample is None or persisted_sample == sample):
                try:
                    self._capability_matrix = self._matrix_from_dict(payload)
                    self._probe_sample_resource_id = sample or persisted_sample
                    return self._capability_matrix
                except (TypeError, ValueError, KeyError):
                    pass

        probe_resource = sample or "__host__"
        grant = self._authorize_mythos("veriflow.probe", probe_resource, "capability_probe")
        matrix = self.ckan.probe_capabilities(sample_resource_id=sample)
        self._capability_matrix = matrix
        self._probe_sample_resource_id = sample
        self._persist_capability_matrix(matrix)
        self._record_mythos(
            grant,
            event_type="capability_probe",
            action="veriflow.probe",
            resource_id=probe_resource,
            metadata={"version": matrix.version.raw, "capability_count": len(matrix.capabilities)},
        )
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

        grant = self._authorize_mythos("veriflow.refresh", resource_id, "dataset_refresh")
        matrix = self.bootstrap(sample_resource_id=resource_id)

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
        if (
            fingerprint_ready
            and existing is not None
            and existing.upstream_fingerprint == upstream_fingerprint
        ):
            self._record_mythos(
                grant,
                event_type="refresh_cache_hit",
                action="veriflow.refresh",
                resource_id=resource_id,
                metadata={"digest": existing.digest, "upstream_fingerprint": existing.upstream_fingerprint},
            )
            return existing

        persisted = self._state.get("resources", {}).get(resource_id, {})
        if (
            fingerprint_ready
            and upstream_fingerprint is not None
            and existing is None
            and isinstance(persisted, Mapping)
            and persisted.get("upstream_fingerprint") == upstream_fingerprint
        ):
            restored = self._restore_persisted_entry(
                resource_id,
                persisted,
                upstream_fingerprint,
            )
            if restored is not None:
                self._cache[resource_id] = restored
                self._record_mythos(
                    grant,
                    event_type="refresh_state_restore",
                    action="veriflow.refresh",
                    resource_id=resource_id,
                    metadata={"digest": restored.digest, "upstream_fingerprint": restored.upstream_fingerprint},
                )
                return restored

        result = self.ckan.ingest_resource(
            resource_id,
            capability_matrix=matrix,
            resource_dict=resource_snapshot,
            package_dict=package_snapshot,
        )
        rows = list(result.rows)
        digest = self._rows_digest(rows)

        if not fingerprint_ready:
            upstream_fingerprint = digest
            fingerprint_payload = {
                "mode": "ingestion_digest_fallback",
                "reason": "upstream fingerprint unavailable",
            }

        if existing is not None and existing.digest == digest:
            existing.fields = list(result.fields)
            existing.package_id = result.package_id
            existing.ingestion_path = result.path
            existing.ingestion_attempts = list(result.attempts)
            existing.ingestion_metadata = dict(result.metadata)
            existing.resource_snapshot = dict(result.resource)
            existing.package_snapshot = dict(result.package) if result.package else None
            existing.upstream_fingerprint = upstream_fingerprint
            existing.upstream_fingerprint_payload = dict(fingerprint_payload)
            self._persist_dataset_entry(existing)
            self._record_mythos(
                grant,
                event_type="refresh_metadata_update",
                action="veriflow.refresh",
                resource_id=resource_id,
                metadata={"digest": existing.digest, "upstream_fingerprint": existing.upstream_fingerprint},
            )
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
        self._persist_dataset_entry(entry)
        self._record_mythos(
            grant,
            event_type="refresh_ingest",
            action="veriflow.refresh",
            resource_id=resource_id,
            metadata={
                "digest": entry.digest,
                "upstream_fingerprint": entry.upstream_fingerprint,
                "ingestion_path": entry.ingestion_path,
                "row_count": len(entry.rows),
            },
        )
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
        grant = self._authorize_mythos("veriflow.answer", resource_id, "question_answer")
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
        self._record_mythos(
            grant,
            event_type="answer",
            action="veriflow.answer",
            resource_id=resource_id,
            metadata={
                "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
                "answer_type": answer.answer_type,
                "ingestion_digest": entry.digest,
            },
        )
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
