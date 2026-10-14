"""Positive-list normalization: credentials, bodies, URLs and headers are discarded."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .models import SecurityFinding, SecurityReport, ToolId, ToolkitError
from .policy import AssessmentScope

MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10_000


def read_evidence(path: str | Path, scope: AssessmentScope) -> bytes:
    source = scope.local_path(path)
    with source.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ToolkitError("Evidence exceeds the byte budget.")
    return data


def _integer(value: Any, low: int = 0, high: int = 10**9) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ToolkitError("Invalid numeric field in evidence.")
    return value


def normalize(tool: ToolId, data: bytes, scope: AssessmentScope, *, mode: str = "import") -> SecurityReport:
    scope.check(tool)
    if len(data) > MAX_BYTES:
        raise ToolkitError("Evidence exceeds the byte budget.")
    digest = hashlib.sha256(data).hexdigest()
    findings: list[SecurityFinding] = []
    seen = 0

    def add(category: str, severity: str, summary: str, **evidence: Any) -> None:
        item = {"source_sha256": digest, **evidence}
        identity = hashlib.sha256(json.dumps([tool.value, category, item], sort_keys=True).encode()).hexdigest()
        findings.append(SecurityFinding(identity, tool, category, severity, summary, item))

    def count() -> None:
        nonlocal seen
        seen += 1
        if seen > MAX_RECORDS:
            raise ToolkitError("Evidence exceeds the record budget.")

    try:
        text = data.decode("utf-8")
        if tool == ToolId.TRUFFLEHOG:
            for line in text.splitlines():
                if not line.strip():
                    continue
                count()
                record = json.loads(line)
                verified = record.get("Verified", False)
                if type(verified) is not bool:
                    raise ToolkitError("Invalid credential verification claim.")
                # DetectorName and source file names are untrusted strings and can contain secrets.
                # Keep a numeric detector identifier, never Raw, RawV2, Redacted or ExtraData.
                detector = _integer(record.get("DetectorType", 0))
                add(
                    "credential_exposure",
                    "high",
                    "Potential credential exposure; review and rotate.",
                    detector_type=detector,
                    tool_claims_verified=verified,
                    record_index=seen,
                )
        elif tool == ToolId.SHERLOCK:
            reader = csv.DictReader(io.StringIO(text))
            if not {"username", "name", "exists"} <= set(reader.fieldnames or []):
                raise ToolkitError("Sherlock CSV is missing required columns.")
            for record in reader:
                count()
                scope.username(record["username"])
                if record["name"] not in scope.sites:
                    raise ToolkitError("Sherlock site is outside the assessment scope.")
                if record["exists"].strip().lower() in {"claimed", "true"}:
                    add(
                        "username_match",
                        "low",
                        "Possible username match; account ownership is unverified.",
                        site=record["name"],
                        username_id=hashlib.sha256(record["username"].encode()).hexdigest(),
                    )
        elif tool == ToolId.GHIDRA:
            record = json.loads(text)
            count()
            if record.get("schema") != "ethos-aegis.ghidra.v1":
                raise ToolkitError("Unsupported Ghidra summary schema.")
            add(
                "binary_inventory",
                "low",
                "Static analysis summary; this does not establish malicious behavior.",
                functions=_integer(record["functions"]),
                imports=_integer(record["imports"]),
                executable_bytes=_integer(record["executable_bytes"]),
            )
        elif tool == ToolId.MITMPROXY:
            if text.lstrip().startswith("{") and '"log"' in text[:256]:
                records = json.loads(text)["log"]["entries"]
                if not isinstance(records, list):
                    raise ToolkitError("Invalid HAR entries.")
                for record in records:
                    count()
                    url = urlsplit(record["request"]["url"])
                    if url.scheme not in {"http", "https"} or url.username or url.password or not url.hostname:
                        raise ToolkitError("Invalid HAR request URL.")
                    host = scope.host(url.hostname)
                    status = _integer(record["response"]["status"], 0, 599)
                    add(
                        "application_egress",
                        "low",
                        "Observed application request; content and credentials were discarded.",
                        host=host,
                        status=status,
                        tls=url.scheme == "https",
                        record_index=seen,
                    )
            else:
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    count()
                    if record.get("schema") != "ethos-aegis.flow.v1" or type(record.get("tls")) is not bool:
                        raise ToolkitError("Unsupported sanitized flow schema.")
                    add(
                        "application_egress",
                        "low",
                        "Observed application request; content and credentials were discarded.",
                        host=scope.host(record["host"]),
                        status=_integer(record["status"], 0, 599),
                        tls=record["tls"],
                        record_index=seen,
                    )
        elif tool == ToolId.MARAUDER:
            for line in text.splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                count()
                if record.get("schema") != "ethos-aegis.marauder.v1":
                    raise ToolkitError("Unsupported Marauder summary schema.")
                if record["device_id"] not in scope.devices:
                    raise ToolkitError("Wireless device is outside the assessment scope.")
                protocol = record["protocol"]
                if protocol not in {"wifi", "bluetooth"}:
                    raise ToolkitError("Unsupported wireless protocol.")
                add(
                    "wireless_inventory",
                    "low",
                    "Authorized device inventory; no radio operation was performed.",
                    device_id=hashlib.sha256(record["device_id"].encode()).hexdigest(),
                    protocol=protocol,
                    observations=_integer(record["observations"]),
                )
        else:
            raise ToolkitError("Unsupported tool.")
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError, csv.Error, ValueError) as exc:
        if isinstance(exc, ToolkitError):
            raise
        raise ToolkitError("Malformed tool evidence.") from None
    # Deduplicate equivalent observations, preserving order and source provenance.
    unique = {item.identifier: item for item in findings}
    return SecurityReport(tool, digest, tuple(unique.values()), seen, mode)
