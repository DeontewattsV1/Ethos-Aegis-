from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional


@dataclass(slots=True)
class SchemaField:
    name: str
    label: str | None = None
    description: str | None = None
    aliases: list[str] = field(default_factory=list)
    unit: str | None = None
    field_type: str | None = None

    def searchable_text(self) -> str:
        parts = [self.name, self.label or "", self.description or "", *self.aliases, self.unit or ""]
        return " ".join(p for p in parts if p).lower()


@dataclass(slots=True, frozen=True)
class CKANVersion:
    raw: str = "unknown"
    major: int | None = None
    minor: int | None = None
    patch: int | None = None
    prerelease: str | None = None

    @classmethod
    def parse(cls, value: str | None) -> "CKANVersion":
        if not value:
            return cls()
        match = re.search(r"(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?(?P<prerelease>[A-Za-z0-9.-]+)?", value)
        if not match:
            return cls(raw=value)
        prerelease = match.group("prerelease") or None
        return cls(
            raw=value,
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch") or 0),
            prerelease=prerelease,
        )

    def at_least(self, major: int, minor: int, patch: int = 0) -> bool:
        if self.major is None or self.minor is None or self.patch is None:
            return False
        return (self.major, self.minor, self.patch) >= (major, minor, patch)

    def is_2_10_or_newer(self) -> bool:
        return self.at_least(2, 10)

    def is_2_11_or_newer(self) -> bool:
        return self.at_least(2, 11)


@dataclass(slots=True)
class ProbeEvidence:
    name: str
    ok: bool
    source: str
    detail: str = ""
    status_code: int | None = None
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class CapabilityRecord:
    name: str
    state: str
    source: str
    detail: str = ""
    evidence: list[ProbeEvidence] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.state in {"available", "inferred"}


@dataclass(slots=True)
class CKANCapabilityMatrix:
    api_base: str
    version: CKANVersion
    capabilities: dict[str, CapabilityRecord]
    discovered_plugins: list[str] = field(default_factory=list)
    supported_actions: list[str] = field(default_factory=list)
    status_payload: dict[str, Any] = field(default_factory=dict)

    def supports(self, capability_name: str, *, include_inferred: bool = True) -> bool:
        record = self.capabilities.get(capability_name)
        if record is None:
            return False
        if include_inferred:
            return record.state in {"available", "inferred"}
        return record.state == "available"

    def get(self, capability_name: str) -> CapabilityRecord | None:
        return self.capabilities.get(capability_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_base": self.api_base,
            "version": {
                "raw": self.version.raw,
                "major": self.version.major,
                "minor": self.version.minor,
                "patch": self.version.patch,
                "prerelease": self.version.prerelease,
            },
            "discovered_plugins": self.discovered_plugins,
            "supported_actions": self.supported_actions,
            "status_payload": self.status_payload,
            "capabilities": {
                name: {
                    "state": record.state,
                    "source": record.source,
                    "detail": record.detail,
                    "available": record.available,
                    "evidence": [
                        {
                            "name": item.name,
                            "ok": item.ok,
                            "source": item.source,
                            "detail": item.detail,
                            "status_code": item.status_code,
                        }
                        for item in record.evidence
                    ],
                }
                for name, record in self.capabilities.items()
            },
        }


@dataclass(slots=True)
class IngestionAttempt:
    path: str
    ok: bool
    detail: str = ""


@dataclass(slots=True)
class CKANIngestionResult:
    resource_id: str
    package_id: str | None
    path: str
    rows: list[dict[str, Any]]
    fields: list[SchemaField]
    resource: dict[str, Any]
    package: dict[str, Any] | None = None
    attempts: list[IngestionAttempt] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CKANClient:
    """
    Version-tolerant CKAN Action API client with capability probing.

    Design target:
    - CKAN 2.11-first
    - CKAN 2.10-compatible
    - plugin-discovery-driven for Table Designer, Scheming, and DCAT
    """

    _CORE_ACTIONS: tuple[str, ...] = (
        "status_show",
        "package_search",
        "package_show",
        "resource_show",
        "organization_list",
        "group_list",
        "tag_list",
    )
    _DATASTORE_ACTIONS: tuple[str, ...] = (
        "datastore_search",
        "datastore_info",
        "datastore_search_sql",
        "datastore_upsert",
    )
    _SCHEMING_ACTIONS: tuple[str, ...] = (
        "scheming_dataset_schemas",
        "scheming_dataset_schema_show",
        "scheming_resource_schema_show",
        "scheming_organization_schema_show",
        "scheming_group_schema_show",
    )
    _DCAT_PATHS: tuple[str, ...] = (
        "/catalog.xml",
        "/catalog.rdf",
        "/catalog.ttl",
        "/catalog.jsonld",
    )

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def status_show(self) -> dict[str, Any]:
        return self._action("status_show", {})

    def help_show(self, action_name: str) -> dict[str, Any]:
        return self._action("help_show", {"name": action_name})

    def package_search(self, query: str = "*:*", rows: int = 10, start: int = 0) -> dict[str, Any]:
        return self._action("package_search", {"q": query, "rows": rows, "start": start})

    def package_show(self, package_id: str) -> dict[str, Any]:
        return self._action("package_show", {"id": package_id})

    def resource_show(self, resource_id: str) -> dict[str, Any]:
        return self._action("resource_show", {"id": resource_id})

    def datastore_info(self, resource_id: str) -> dict[str, Any]:
        return self._action("datastore_info", {"id": resource_id})

    def datastore_search(
        self,
        resource_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        filters: Optional[dict[str, Any]] = None,
        fields: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"resource_id": resource_id, "limit": limit, "offset": offset}
        if filters:
            payload["filters"] = filters
        if fields:
            payload["fields"] = fields
        return self._action("datastore_search", payload)

    def infer_schema_fields(
        self,
        package_dict: Mapping[str, Any],
        resource_dict: Mapping[str, Any] | None = None,
    ) -> list[SchemaField]:
        resources = package_dict.get("resources") or ([] if resource_dict is None else [resource_dict])
        fields: list[SchemaField] = []
        for resource in resources:
            schema_rows = resource.get("schema") or resource.get("fields") or resource.get("table_schema") or []
            for item in schema_rows:
                if not isinstance(item, Mapping):
                    continue
                fields.append(
                    SchemaField(
                        name=str(item.get("id") or item.get("name") or "unknown"),
                        label=self._first_str(item, "label", "title"),
                        description=self._first_str(item, "info", "description", "notes"),
                        aliases=list(item.get("aliases") or []),
                        unit=self._first_str(item, "unit"),
                        field_type=self._first_str(item, "type", "field_type"),
                    )
                )
        return fields

    def compute_upstream_fingerprint(
        self,
        resource_id: str,
        *,
        capability_matrix: CKANCapabilityMatrix | None = None,
        fingerprint_mode: str = "auto",
        row_signature_limit: int = 10,
        row_signature_fields: list[str] | None = None,
        resource_dict: Mapping[str, Any] | None = None,
        package_dict: Mapping[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        resource_payload = dict(resource_dict) if resource_dict is not None else dict((self.resource_show(resource_id).get("result") or {}))
        package_payload: dict[str, Any] | None
        if package_dict is not None:
            package_payload = dict(package_dict)
        else:
            package_id = resource_payload.get("package_id") or resource_payload.get("package")
            if package_id:
                try:
                    package_payload = dict((self.package_show(str(package_id)).get("result") or {}))
                except Exception:
                    package_payload = None
            else:
                package_payload = None

        effective_mode = fingerprint_mode
        if fingerprint_mode == "auto":
            datastore_active = bool(resource_payload.get("datastore_active"))
            datastore_supported = bool(capability_matrix and capability_matrix.supports("datastore"))
            effective_mode = "datastore_lightweight" if datastore_active and datastore_supported else "metadata"

        payload: dict[str, Any] = {
            "mode": effective_mode,
            "resource": self._metadata_subset(resource_payload),
            "package": self._metadata_subset(package_payload or {}),
        }

        if effective_mode == "datastore_lightweight" and bool(resource_payload.get("datastore_active")):
            try:
                info = (self.datastore_info(resource_id).get("result") or {})
                search = (self.datastore_search(resource_id, limit=row_signature_limit, fields=row_signature_fields).get("result") or {})
                rows = [dict(row) for row in (search.get("records") or []) if isinstance(row, Mapping)]
                row_hashes = [self._stable_hash(row) for row in rows]
                payload["row_signature"] = {
                    "fields": [field.get("id") or field.get("name") for field in (info.get("fields") or []) if isinstance(field, Mapping)],
                    "total": search.get("total"),
                    "sample_hashes": row_hashes,
                    "limit": row_signature_limit,
                    "selected_fields": list(row_signature_fields or []),
                }
            except Exception as error:
                payload["row_signature_error"] = str(error)

        return self._stable_hash(payload), payload, resource_payload, package_payload

    def ingest_resource(
        self,
        resource_id: str,
        *,
        capability_matrix: CKANCapabilityMatrix | None = None,
        limit: int = 100,
        offset: int = 0,
        filters: Optional[dict[str, Any]] = None,
        field_names: Optional[list[str]] = None,
        resource_dict: Mapping[str, Any] | None = None,
        package_dict: Mapping[str, Any] | None = None,
    ) -> CKANIngestionResult:
        resource_payload = dict(resource_dict) if resource_dict is not None else dict((self.resource_show(resource_id).get("result") or {}))
        package_payload: dict[str, Any] | None
        package_id = resource_payload.get("package_id") or resource_payload.get("package")
        if package_dict is not None:
            package_payload = dict(package_dict)
        elif package_id:
            try:
                package_payload = dict((self.package_show(str(package_id)).get("result") or {}))
            except Exception:
                package_payload = None
        else:
            package_payload = None

        attempts: list[IngestionAttempt] = []
        for path_name in self._ordered_ingestion_paths(capability_matrix, resource_dict=resource_payload, package_dict=package_payload):
            try:
                if path_name == "datastore":
                    result = self._ingest_via_datastore(
                        resource_id,
                        package_id=str(package_id) if package_id else None,
                        resource_dict=resource_payload,
                        package_dict=package_payload,
                        limit=limit,
                        offset=offset,
                        filters=filters,
                        field_names=field_names,
                    )
                elif path_name == "resource_schema":
                    result = self._ingest_via_resource_schema(
                        resource_id,
                        package_id=str(package_id) if package_id else None,
                        resource_dict=resource_payload,
                        package_dict=package_payload,
                    )
                else:
                    result = self._ingest_via_metadata(
                        resource_id,
                        package_id=str(package_id) if package_id else None,
                        resource_dict=resource_payload,
                        package_dict=package_payload,
                    )
                result.attempts = [*attempts, IngestionAttempt(path_name, True, f"selected {path_name}")]
                return result
            except Exception as error:
                attempts.append(IngestionAttempt(path_name, False, str(error)))

        fallback = self._ingest_via_metadata(
            resource_id,
            package_id=str(package_id) if package_id else None,
            resource_dict=resource_payload,
            package_dict=package_payload,
        )
        fallback.attempts = [*attempts, IngestionAttempt("metadata_fallback", True, "selected metadata_fallback")]
        return fallback

    def _ordered_ingestion_paths(
        self,
        capability_matrix: CKANCapabilityMatrix | None,
        *,
        resource_dict: Mapping[str, Any],
        package_dict: Mapping[str, Any] | None,
    ) -> list[str]:
        paths: list[str] = []
        schema_fields = self.infer_schema_fields(package_dict or {}, resource_dict)
        datastore_hint = bool(resource_dict.get("datastore_active"))
        datastore_supported = datastore_hint or bool(capability_matrix and capability_matrix.supports("datastore"))
        schema_supported = bool(schema_fields or self._inline_rows_from_resource(resource_dict))

        if datastore_supported:
            paths.append("datastore")
        if schema_supported:
            paths.append("resource_schema")
        paths.append("metadata_fallback")
        return paths

    def _ingest_via_datastore(
        self,
        resource_id: str,
        *,
        package_id: str | None,
        resource_dict: Mapping[str, Any],
        package_dict: Mapping[str, Any] | None,
        limit: int,
        offset: int,
        filters: Optional[dict[str, Any]],
        field_names: Optional[list[str]],
    ) -> CKANIngestionResult:
        info_result = (self.datastore_info(resource_id).get("result") or {})
        search_result = (self.datastore_search(resource_id, limit=limit, offset=offset, filters=filters, fields=field_names).get("result") or {})
        rows = [dict(row) for row in (search_result.get("records") or []) if isinstance(row, Mapping)]
        fields = self._fields_from_schema_items(info_result.get("fields") or [])
        if not fields and rows:
            fields = self._fields_from_rows(rows)
        if not fields and not rows:
            raise RuntimeError("DataStore probe succeeded but returned no fields or records.")
        return CKANIngestionResult(
            resource_id=resource_id,
            package_id=package_id,
            path="datastore",
            rows=rows,
            fields=fields,
            resource=dict(resource_dict),
            package=dict(package_dict) if package_dict else None,
            metadata={"source": "datastore", "total": search_result.get("total")},
        )

    def _ingest_via_resource_schema(
        self,
        resource_id: str,
        *,
        package_id: str | None,
        resource_dict: Mapping[str, Any],
        package_dict: Mapping[str, Any] | None,
    ) -> CKANIngestionResult:
        rows = self._inline_rows_from_resource(resource_dict)
        fields = self.infer_schema_fields(package_dict or {}, resource_dict)
        if not fields and rows:
            fields = self._fields_from_rows(rows)
        if not fields and not rows:
            raise RuntimeError("No resource schema, table schema, or inline rows were available.")
        return CKANIngestionResult(
            resource_id=resource_id,
            package_id=package_id,
            path="resource_schema",
            rows=rows,
            fields=fields,
            resource=dict(resource_dict),
            package=dict(package_dict) if package_dict else None,
            metadata={"source": "resource_schema", "total": len(rows)},
        )

    def _ingest_via_metadata(
        self,
        resource_id: str,
        *,
        package_id: str | None,
        resource_dict: Mapping[str, Any],
        package_dict: Mapping[str, Any] | None,
    ) -> CKANIngestionResult:
        row = self._metadata_row(resource_dict, package_dict)
        return CKANIngestionResult(
            resource_id=resource_id,
            package_id=package_id,
            path="metadata_fallback",
            rows=[row],
            fields=self._fields_from_rows([row]),
            resource=dict(resource_dict),
            package=dict(package_dict) if package_dict else None,
            metadata={"source": "metadata_fallback", "total": 1},
        )

    def _fields_from_schema_items(self, items: Iterable[Mapping[str, Any]]) -> list[SchemaField]:
        fields: list[SchemaField] = []
        for item in items:
            fields.append(
                SchemaField(
                    name=str(item.get("id") or item.get("name") or "unknown"),
                    label=self._first_str(item, "label", "title"),
                    description=self._first_str(item, "description", "info", "notes"),
                    field_type=self._first_str(item, "type", "field_type"),
                )
            )
        return fields

    def _fields_from_rows(self, rows: list[Mapping[str, Any]]) -> list[SchemaField]:
        names: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row.keys():
                key_str = str(key)
                if key_str not in seen:
                    seen.add(key_str)
                    names.append(key_str)
        return [SchemaField(name=name) for name in names]

    def _inline_rows_from_resource(self, resource_dict: Mapping[str, Any]) -> list[dict[str, Any]]:
        for key in ("records", "rows", "data"):
            value = resource_dict.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, Mapping)]
        return []

    def _metadata_row(self, resource_dict: Mapping[str, Any], package_dict: Mapping[str, Any] | None) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for prefix, payload in (("resource", resource_dict), ("package", package_dict or {})):
            for key, value in payload.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    row[f"{prefix}_{key}"] = value
        return row

    def probe_capabilities(self, *, sample_resource_id: str | None = None) -> CKANCapabilityMatrix:
        status_probe = self._safe_action("status_show", {})
        status_payload = (status_probe.payload or {}).get("result") or {}
        version = CKANVersion.parse(str(status_payload.get("ckan_version") or "unknown"))

        plugin_names = sorted(self._extract_plugin_names(status_payload))
        actions_supported: list[str] = []
        action_evidence: dict[str, ProbeEvidence] = {}
        for action_name in (*self._CORE_ACTIONS, *self._DATASTORE_ACTIONS, *self._SCHEMING_ACTIONS):
            evidence = self._probe_action_support(action_name)
            action_evidence[action_name] = evidence
            if evidence.ok:
                actions_supported.append(action_name)

        sample_evidence: ProbeEvidence | None = None
        sample_resource_payload: dict[str, Any] | None = None
        if sample_resource_id:
            sample_evidence = self._safe_action("resource_show", {"id": sample_resource_id})
            if sample_evidence.ok and sample_evidence.payload:
                sample_resource_payload = sample_evidence.payload.get("result") or {}

        dcat_evidence = [self._safe_get(path) for path in self._DCAT_PATHS]

        capabilities = {
            "core_catalog": self._build_core_catalog_record(status_probe, action_evidence),
            "governance": self._build_governance_record(action_evidence),
            "datastore": self._build_datastore_record(action_evidence, sample_resource_payload),
            "table_designer": self._build_table_designer_record(version, plugin_names, action_evidence, sample_resource_payload),
            "scheming": self._build_scheming_record(plugin_names, action_evidence),
            "dcat": self._build_dcat_record(plugin_names, dcat_evidence),
        }

        if sample_evidence is not None and sample_resource_id:
            capabilities["sample_resource"] = CapabilityRecord(
                name="sample_resource",
                state="available" if sample_evidence.ok else "unavailable",
                source="action:resource_show",
                detail=f"Sample resource probe for {sample_resource_id}",
                evidence=[sample_evidence],
            )

        return CKANCapabilityMatrix(
            api_base=f"{self.base_url}/api/3/action",
            version=version,
            capabilities=capabilities,
            discovered_plugins=plugin_names,
            supported_actions=sorted(actions_supported),
            status_payload=status_payload,
        )

    def _build_core_catalog_record(
        self,
        status_probe: ProbeEvidence,
        action_evidence: Mapping[str, ProbeEvidence],
    ) -> CapabilityRecord:
        evidence = [status_probe]
        evidence.extend(action_evidence[name] for name in ("package_search", "package_show", "resource_show"))
        ok = status_probe.ok and all(action_evidence[name].ok for name in ("package_search", "package_show", "resource_show"))
        return CapabilityRecord(
            name="core_catalog",
            state="available" if ok else "partial" if status_probe.ok else "unavailable",
            source="action_api",
            detail="status_show + package/resource actions reachable on /api/3/action",
            evidence=evidence,
        )

    def _build_governance_record(self, action_evidence: Mapping[str, ProbeEvidence]) -> CapabilityRecord:
        evidence = [action_evidence[name] for name in ("organization_list", "group_list", "tag_list")]
        ok_count = sum(1 for item in evidence if item.ok)
        state = "available" if ok_count == len(evidence) else "partial" if ok_count else "unavailable"
        return CapabilityRecord(
            name="governance",
            state=state,
            source="action_api",
            detail="organization, group, and tag surfaces",
            evidence=evidence,
        )

    def _build_datastore_record(
        self,
        action_evidence: Mapping[str, ProbeEvidence],
        sample_resource_payload: Mapping[str, Any] | None,
    ) -> CapabilityRecord:
        evidence = [action_evidence[name] for name in ("datastore_search", "datastore_info")]
        if sample_resource_payload is not None:
            evidence.append(
                ProbeEvidence(
                    name="sample_resource_schema",
                    ok=bool(sample_resource_payload.get("schema") or sample_resource_payload.get("fields") or sample_resource_payload.get("datastore_active")),
                    source="sample_resource",
                    detail="Resource exposes schema, fields, or datastore_active metadata.",
                    payload=dict(sample_resource_payload),
                )
            )
        search_ok = action_evidence["datastore_search"].ok
        info_ok = action_evidence["datastore_info"].ok
        state = "available" if search_ok and info_ok else "partial" if search_ok or info_ok else "unavailable"
        return CapabilityRecord(
            name="datastore",
            state=state,
            source="action_api",
            detail="DataStore-backed structured query layer",
            evidence=evidence,
        )

    def _build_table_designer_record(
        self,
        version: CKANVersion,
        plugin_names: Iterable[str],
        action_evidence: Mapping[str, ProbeEvidence],
        sample_resource_payload: Mapping[str, Any] | None,
    ) -> CapabilityRecord:
        plugin_set = {plugin.lower() for plugin in plugin_names}
        evidence: list[ProbeEvidence] = []
        datastore_ok = action_evidence["datastore_search"].ok or action_evidence["datastore_info"].ok
        if any(token in plugin_set for token in {"tabledesigner", "ckanext-tabledesigner"}):
            evidence.append(ProbeEvidence("tabledesigner_plugin", True, "plugin", detail="Table Designer plugin advertised by host."))
            return CapabilityRecord(
                name="table_designer",
                state="available",
                source="plugin",
                detail="Explicit Table Designer plugin discovered.",
                evidence=evidence,
            )
        if sample_resource_payload:
            has_schema = bool(sample_resource_payload.get("schema") or sample_resource_payload.get("fields") or sample_resource_payload.get("table_schema"))
            if has_schema:
                evidence.append(
                    ProbeEvidence(
                        name="sample_resource_schema",
                        ok=True,
                        source="sample_resource",
                        detail="Sample resource advertises schema metadata compatible with table design workflows.",
                        payload=dict(sample_resource_payload),
                    )
                )
        if version.is_2_11_or_newer() and datastore_ok:
            evidence.append(
                ProbeEvidence(
                    name="version_inference",
                    ok=True,
                    source="version+datastore",
                    detail=f"CKAN {version.raw} with DataStore present; Table Designer support inferred.",
                )
            )
            return CapabilityRecord(
                name="table_designer",
                state="inferred",
                source="version+datastore",
                detail="Inferred from 2.11+ and DataStore presence.",
                evidence=evidence,
            )
        evidence.append(ProbeEvidence(name="table_designer_probe", ok=False, source="version+plugin", detail="No explicit Table Designer signal found."))
        return CapabilityRecord(
            name="table_designer",
            state="unavailable",
            source="version+plugin",
            detail="No explicit or inferable Table Designer capability detected.",
            evidence=evidence,
        )

    def _build_scheming_record(
        self,
        plugin_names: Iterable[str],
        action_evidence: Mapping[str, ProbeEvidence],
    ) -> CapabilityRecord:
        plugin_set = {plugin.lower() for plugin in plugin_names}
        evidence = [action_evidence[name] for name in self._SCHEMING_ACTIONS]
        if any("scheming" in plugin for plugin in plugin_set):
            evidence.append(ProbeEvidence(name="scheming_plugin", ok=True, source="plugin", detail="Scheming plugin advertised by host."))
        ok_count = sum(1 for item in evidence if item.ok)
        state = "available" if ok_count else "unavailable"
        source = "action_api" if ok_count and any(item.source == "action:help_show" for item in evidence if item.ok) else "plugin"
        return CapabilityRecord(
            name="scheming",
            state=state,
            source=source,
            detail="Schema-definition and schema-introspection surface",
            evidence=evidence,
        )

    def _build_dcat_record(self, plugin_names: Iterable[str], dcat_evidence: Iterable[ProbeEvidence]) -> CapabilityRecord:
        plugin_set = {plugin.lower() for plugin in plugin_names}
        evidence = list(dcat_evidence)
        if any("dcat" in plugin for plugin in plugin_set):
            evidence.append(ProbeEvidence(name="dcat_plugin", ok=True, source="plugin", detail="DCAT plugin advertised by host."))
        ok = any(item.ok for item in evidence)
        return CapabilityRecord(
            name="dcat",
            state="available" if ok else "unavailable",
            source="http_probe" if ok else "plugin+http_probe",
            detail="DCAT and RDF catalog exposure",
            evidence=evidence,
        )

    def _extract_plugin_names(self, status_payload: Mapping[str, Any]) -> set[str]:
        plugin_names: set[str] = set()
        for key in ("site_url", "ckan_site_url", "plugins", "ckan.plugins"):
            value = status_payload.get(key)
            if isinstance(value, str) and " " in value:
                plugin_names.update(token.strip() for token in value.split() if token.strip())
            elif isinstance(value, str) and value:
                plugin_names.add(value.strip())
            elif isinstance(value, Iterable) and not isinstance(value, (bytes, str)):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        plugin_names.add(item.strip())
        return plugin_names

    def _probe_action_support(self, action_name: str) -> ProbeEvidence:
        probe = self._safe_action("help_show", {"name": action_name})
        if probe.ok:
            return ProbeEvidence(
                name=action_name,
                ok=True,
                source="action:help_show",
                detail=f"Action {action_name} advertised by help_show.",
                status_code=probe.status_code,
                payload=probe.payload,
            )
        return ProbeEvidence(
            name=action_name,
            ok=False,
            source="action:help_show",
            detail=probe.detail,
            status_code=probe.status_code,
            payload=probe.payload,
        )

    def _safe_action(self, action: str, payload: dict[str, Any]) -> ProbeEvidence:
        url = f"{self.base_url}/api/3/action/{action}"
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("User-Agent", "ethos-aegis-veriflow/1.2")
        if self.api_key:
            request.add_header("Authorization", self.api_key)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                parsed = json.loads(body)
                return ProbeEvidence(
                    name=action,
                    ok=bool(parsed.get("success", True)),
                    source=f"action:{action}",
                    detail="request completed",
                    status_code=getattr(response, "status", None),
                    payload=parsed,
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="ignore")
            return ProbeEvidence(name=action, ok=False, source=f"action:{action}", detail=detail or str(error), status_code=error.code)
        except Exception as error:
            return ProbeEvidence(name=action, ok=False, source=f"action:{action}", detail=str(error), status_code=None)

    def _safe_get(self, path: str) -> ProbeEvidence:
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(url, method="GET")
        request.add_header("User-Agent", "ethos-aegis-veriflow/1.2")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                ok = status is None or 200 <= status < 400
                return ProbeEvidence(name=path, ok=ok, source="http_get", detail="endpoint reachable", status_code=status)
        except urllib.error.HTTPError as error:
            return ProbeEvidence(name=path, ok=False, source="http_get", detail=str(error), status_code=error.code)
        except Exception as error:
            return ProbeEvidence(name=path, ok=False, source="http_get", detail=str(error), status_code=None)

    def _action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        probe = self._safe_action(action, payload)
        if not probe.ok or probe.payload is None:
            raise RuntimeError(probe.detail or f"CKAN action failed: {action}")
        return probe.payload

    @staticmethod
    def _first_str(item: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _metadata_subset(payload: Mapping[str, Any]) -> dict[str, Any]:
        subset: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                subset[key] = value
        return subset

    @staticmethod
    def _stable_hash(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
