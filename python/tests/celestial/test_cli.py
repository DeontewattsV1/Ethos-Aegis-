"""Smoke tests for the `celestial` CLI."""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from ethos_aegis.celestial.cli import main

pytest.importorskip("cryptography")


SAMPLE_SPEC = {
    "schema_version": "1.0",
    "creator": "cli-test",
    "system_role": "policy-guardian",
    "use_case": "CLI smoke test",
    "business_goal": "verify CLI round-trips",
    "users": ["operators"],
    "inputs": ["spec.json"],
    "tools": ["pack", "unpack"],
    "responsibilities": ["sign", "encrypt"],
    "memory_requirements": "stateless",
    "constraints": {
        "tech_stack": "Python",
        "model_provider": "n/a",
        "budget": "low",
        "latency": "fast",
        "security_privacy": "high",
        "deployment_target": "containerised",
    },
    "required_output": ["pack.json"],
    "success_criteria": "exit 0",
}


def test_encode_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["encode", "--seed", "cli-seed", "--message", "hello"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out
    assert "hello" not in out  # should be glyphs


def test_decode_round_trip(capsys: pytest.CaptureFixture[str]) -> None:
    main(["encode", "--seed", "cli-seed", "--message", "round-trip"])
    encoded = capsys.readouterr().out.strip()

    rc = main(["decode", "--seed", "cli-seed", "--message", encoded])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "round-trip"


def test_pack_then_unpack(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    pack_file = tmp_path / "pack.json"
    restored_file = tmp_path / "restored.json"
    spec_file.write_text(json.dumps(SAMPLE_SPEC), encoding="utf-8")
    passphrase = secrets.token_urlsafe(32)

    rc_pack = main([
        "pack",
        "--spec-file", str(spec_file),
        "--passphrase", passphrase,
        "--output", str(pack_file),
    ])
    assert rc_pack == 0
    assert pack_file.exists()

    rc_unpack = main([
        "unpack",
        "--pack-file", str(pack_file),
        "--passphrase", passphrase,
        "--output", str(restored_file),
    ])
    assert rc_unpack == 0
    assert json.loads(restored_file.read_text(encoding="utf-8")) == SAMPLE_SPEC


def test_python_dash_m_entrypoint(tmp_path: Path) -> None:
    """`python -m ethos_aegis.celestial` should expose the same CLI."""
    result = subprocess.run(
        [sys.executable, "-m", "ethos_aegis.celestial",
         "encode", "--seed", "module-entry", "--message", "abc"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
