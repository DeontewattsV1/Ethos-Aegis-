"""Regression tests for scope, confidential evidence and external execution boundaries."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from ethos_aegis.security_toolkit import AssessmentScope, BoundedProcessRunner, SecurityToolkit, ToolId, ToolkitError
from ethos_aegis.security_toolkit.__main__ import main
from ethos_aegis.security_toolkit.demo import FIXTURES, demo_scope, run_demo
from ethos_aegis.security_toolkit.parsers import MAX_BYTES, normalize


@pytest.mark.parametrize("tool", list(ToolId))
def test_import_all_five_tools_with_provenance_and_unverified_confidence(tmp_path: Path, tool: ToolId):
    source = tmp_path / "evidence.txt"
    source.write_bytes(FIXTURES[tool])
    report = SecurityToolkit(demo_scope(tmp_path)).import_report(tool, source)
    assert report.records_seen == 1
    assert len(report.source_sha256) == 64
    assert len(report.findings) == 1
    assert report.findings[0].confidence == "tool_reported"
    assert report.findings[0].to_candidate().confidence.value == "hypothesis"
    assert report.to_dict()["tool"] == tool.value


def test_secret_fields_never_reach_export(tmp_path: Path):
    secret = "PRIVATE_SENTINEL_VALUE_ABC123"
    raw = json.dumps(
        {
            "Verified": True,
            "DetectorType": 2,
            "DetectorName": secret,
            "Raw": secret,
            "RawV2": secret,
            "Redacted": secret,
            "ExtraData": {"account": secret},
            "SourceMetadata": {"Data": {"Git": {"file": secret}}},
        }
    ).encode()
    report = normalize(ToolId.TRUFFLEHOG, raw, demo_scope(tmp_path))
    assert secret not in json.dumps(report.to_dict())
    assert report.findings[0].evidence["tool_claims_verified"] is True
    assert report.findings[0].confidence != "verified"


def test_har_discards_credentials_bodies_queries_and_headers(tmp_path: Path):
    secret = "PRIVATE_HTTP_SENTINEL"
    data = {
        "log": {
            "entries": [
                {
                    "request": {
                        "url": f"https://app.example.test/path?token={secret}",
                        "headers": [{"name": "Authorization", "value": secret}],
                        "postData": {"text": secret},
                    },
                    "response": {"status": 200, "content": {"text": secret}},
                }
            ]
        }
    }
    report = normalize(ToolId.MITMPROXY, json.dumps(data).encode(), demo_scope(tmp_path))
    assert secret not in json.dumps(report.to_dict())
    assert report.findings[0].evidence["host"] == "app.example.test"


@pytest.mark.parametrize(
    "tool,data",
    [
        (ToolId.TRUFFLEHOG, b'{"DetectorType":"SECRET","Verified":false}'),
        (ToolId.SHERLOCK, b"username,name,exists\noutsider,GitHub,Claimed\n"),
        (ToolId.SHERLOCK, b"username,name,exists\nethos_demo,Unapproved,Claimed\n"),
        (ToolId.MITMPROXY, b'{"schema":"ethos-aegis.flow.v1","host":"outside.test","status":200,"tls":true}'),
        (
            ToolId.MARAUDER,
            b'{"schema":"ethos-aegis.marauder.v1","device_id":"outsider","protocol":"wifi","observations":1}',
        ),
        (ToolId.GHIDRA, b'{"schema":"ethos-aegis.ghidra.v1","functions":-1,"imports":1,"executable_bytes":1}'),
    ],
)
def test_invalid_or_out_of_scope_records_fail_closed(tmp_path: Path, tool: ToolId, data: bytes):
    with pytest.raises(ToolkitError):
        normalize(tool, data, demo_scope(tmp_path))


@pytest.mark.parametrize("tool", list(ToolId))
def test_invalid_output_has_fixed_error_without_raw_data(tmp_path: Path, tool: ToolId):
    with pytest.raises(ToolkitError) as failure:
        normalize(tool, b"PRIVATE_BAD_OUTPUT", demo_scope(tmp_path))
    assert "PRIVATE_BAD_OUTPUT" not in str(failure.value)


def test_byte_and_record_limits(tmp_path: Path):
    scope = demo_scope(tmp_path)
    with pytest.raises(ToolkitError, match="byte budget"):
        normalize(ToolId.TRUFFLEHOG, b"x" * (MAX_BYTES + 1), scope)
    with pytest.raises(ToolkitError, match="record budget"):
        normalize(ToolId.TRUFFLEHOG, b'{"DetectorType":0}\n' * 10_001, scope)


def test_expired_and_disallowed_scope(tmp_path: Path):
    for scope in (
        replace(demo_scope(tmp_path), expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)),
        replace(demo_scope(tmp_path), allowed_tools=()),
    ):
        with pytest.raises(ToolkitError):
            normalize(ToolId.TRUFFLEHOG, b"", scope)


def test_scope_manifest_rejects_string_boolean_and_relative_roots(tmp_path: Path):
    data = {
        "authorization_reference": "local-test",
        "expires_at": "2099-01-01T00:00:00Z",
        "allowed_tools": ["trufflehog"],
        "local_roots": [str(tmp_path)],
        "allow_network": "false",
    }
    with pytest.raises(ToolkitError):
        AssessmentScope.from_dict(data)
    data["allow_network"] = False
    data["local_roots"] = ["."]
    with pytest.raises(ToolkitError):
        AssessmentScope.from_dict(data)


def test_canonical_paths_block_sibling_prefixes_and_symlink_escape(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    sibling = tmp_path / "allowed-other"
    sibling.mkdir()
    outside = sibling / "data.json"
    outside.write_text("{}")
    scope = replace(demo_scope(tmp_path), local_roots=(root,))
    with pytest.raises(ToolkitError):
        scope.local_path(outside)
    try:
        (root / "linked.json").symlink_to(outside)
    except OSError:
        pytest.skip("Platform does not permit test symlink creation")
    with pytest.raises(ToolkitError):
        scope.local_path(root / "linked.json")


class SpyRunner:
    def __init__(self, tool: ToolId):
        self.tool = tool
        self.calls = []

    def run(self, argv, cwd):
        self.calls.append(argv)
        if self.tool == ToolId.SHERLOCK:
            (cwd / "ethos_demo.csv").write_bytes(FIXTURES[self.tool])
        if self.tool == ToolId.GHIDRA:
            (cwd / "summary.json").write_bytes(FIXTURES[self.tool])
        return FIXTURES[self.tool]


@pytest.mark.parametrize("tool", [ToolId.TRUFFLEHOG, ToolId.SHERLOCK, ToolId.GHIDRA])
def test_execution_requires_scope_and_builds_shell_free_fixed_argv(tmp_path: Path, tool: ToolId):
    target = tmp_path / "binary.bin"
    target.write_bytes(b"synthetic")
    value = "ethos_demo" if tool == ToolId.SHERLOCK else str(tmp_path if tool == ToolId.TRUFFLEHOG else target)
    spy = SpyRunner(tool)
    scope = demo_scope(tmp_path)
    toolkit = SecurityToolkit(scope, spy)
    toolkit.plan(tool, value)
    assert not spy.calls
    with pytest.raises(ToolkitError, match="execution is not authorized"):
        toolkit.execute(tool, value, sys.executable)
    assert not spy.calls
    scope = replace(scope, allow_execution=True, allow_network=tool == ToolId.SHERLOCK)
    report = SecurityToolkit(scope, spy).execute(tool, value, sys.executable)
    assert report.mode == "execution"
    assert len(spy.calls) == 1
    if tool == ToolId.TRUFFLEHOG:
        assert "--no-verification" in spy.calls[0] and "--no-update" in spy.calls[0]
    if tool == ToolId.SHERLOCK:
        assert spy.calls[0][-2:] == ["--site", "GitHub"]
        assert "--local" in spy.calls[0]
    if tool == ToolId.GHIDRA:
        assert "-deleteProject" in spy.calls[0] and "-analysisTimeoutPerFile" in spy.calls[0]


def test_network_denied_before_sherlock_process_launch(tmp_path: Path):
    spy = SpyRunner(ToolId.SHERLOCK)
    scope = replace(demo_scope(tmp_path), allow_execution=True)
    with pytest.raises(ToolkitError, match="Network access is not authorized"):
        SecurityToolkit(scope, spy).execute(ToolId.SHERLOCK, "ethos_demo", sys.executable)
    assert not spy.calls


@pytest.mark.parametrize("tool", [ToolId.MITMPROXY, ToolId.MARAUDER])
def test_radio_and_proxy_integrations_cannot_execute(tmp_path: Path, tool: ToolId):
    with pytest.raises(ToolkitError, match="import only"):
        SecurityToolkit(demo_scope(tmp_path)).plan(tool, str(tmp_path))


def test_process_timeout_output_limit_and_error_redaction(tmp_path: Path):
    runner = BoundedProcessRunner(timeout=0.3, max_bytes=100)
    with pytest.raises(ToolkitError, match="time budget"):
        runner.run([sys.executable, "-c", "import time; time.sleep(2)"], tmp_path)
    with pytest.raises(ToolkitError, match="byte budget"):
        runner.run([sys.executable, "-c", "print('x'*10000)"], tmp_path)
    with pytest.raises(ToolkitError) as failure:
        runner.run([sys.executable, "-c", "import sys; print('PRIVATE_FAILURE'); sys.exit(1)"], tmp_path)
    assert "PRIVATE_FAILURE" not in str(failure.value)


@pytest.mark.parametrize("scenario", ["toolkit", "immune", "veriflow"])
def test_offline_walkthroughs_execute(scenario, capsys):
    run_demo(scenario)
    output = capsys.readouterr().out
    assert "Synthetic inputs" in output
    assert "PRIVATE_COOKIE" not in output


def test_cli_catalog_and_bad_scope_have_predictable_exit_status(tmp_path, capsys):
    assert main(["catalog"]) == 0
    assert "headless runner" in capsys.readouterr().out
    scope = tmp_path / "invalid.json"
    scope.write_text("PRIVATE_INVALID_SCOPE")
    assert main(["import", "trufflehog", "report.json", "--scope", str(scope)]) == 2
    assert "PRIVATE_INVALID_SCOPE" not in capsys.readouterr().err
