from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ethos_aegis.agent.scaffolds.task_verifier_mesh import DeterministicVerifier

from .ckan_adapter import CKANCapabilityMatrix, CKANClient, SchemaField
from .question_answering import AnswerRecord, VeriflowReasoner


@dataclass(slots=True)
class DatasetCacheEntry:
    resource_id: str
    digest: str
    rows: list[dict[str, Any]]
    fields: list[SchemaField]
    last_answer: Optional[AnswerRecord] = None


class VeriflowImmuneSystem:
    """
    Agentic data immune system for CKAN-backed knowledge hubs.

    Flow:
        CKAN resource -> startup capability probe -> digest check -> deterministic verifier -> formula cache -> answer engine
    """

    def __init__(
        self,
        ckan: CKANClient,
        verifier: DeterministicVerifier | None = None,
        reasoner: VeriflowReasoner | None = None,
        *,
        probe_on_startup: bool = True,
        sample_resource_id: str | None = None,
    ) -> None:
        self.ckan = ckan
        self.verifier = verifier or DeterministicVerifier()
        self.reasoner = reasoner or VeriflowReasoner()
        self._cache: dict[str, DatasetCacheEntry] = {}
        self._capability_matrix: CKANCapabilityMatrix | None = None
        self._probe_sample_resource_id = sample_resource_id
        if probe_on_startup:
            self.bootstrap(sample_resource_id=sample_resource_id)

    @property
    def capability_matrix(self) -> CKANCapabilityMatrix | None:
        return self._capability_matrix

    def bootstrap(self, *, sample_resource_id: str | None = None, force: bool = False) -> CKANCapabilityMatrix:
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

    def refresh_resource(
        self,
        package_dict: Mapping[str, Any],
        resource_id: str,
        rows: list[dict[str, Any]],
        fields: list[SchemaField],
    ) -> DatasetCacheEntry:
        if self._capability_matrix is None or (self._probe_sample_resource_id is None and resource_id):
            self.bootstrap(sample_resource_id=resource_id, force=self._probe_sample_resource_id is None and bool(resource_id))

        digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()
        existing = self._cache.get(resource_id)
        if existing and existing.digest == digest:
            return existing

        verification = self.verifier.verify_source_snapshot(json.dumps(rows))
        if not verification.passed and verification.issue_type == "syntax_error":
            raise ValueError("Dataset cache failed deterministic serialization verification.")

        entry = DatasetCacheEntry(resource_id=resource_id, digest=digest, rows=rows, fields=fields)
        self._cache[resource_id] = entry
        return entry

    def answer_question(self, resource_id: str, question: str, *, target_field: str | None = None) -> AnswerRecord:
        if resource_id not in self._cache:
            raise KeyError(f"Resource {resource_id!r} has not been refreshed into cache.")
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
        entry.last_answer = answer
        return answer
