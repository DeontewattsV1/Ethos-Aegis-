"""Isolated security and correctness regressions for opt-in Mythos utilities."""
import os
from pathlib import Path
import pytest
from ethos_aegis.mythos_runtime import BudgetExceeded, BudgetMeter, DriftDetector, MemoryLedger, StrictWriteDiscipline
from ethos_aegis.mythos_runtime.cli import main


def test_budget_denies_overage_without_consumption():
    meter = BudgetMeter(max_tokens=10, max_turns=2)
    meter.consume(tokens=7, turns=1)
    with pytest.raises(BudgetExceeded):
        meter.consume(tokens=4, turns=1)
    assert (meter.tokens_used, meter.turns_used) == (7, 1)
    with pytest.raises(ValueError):
        meter.consume(tokens=-1)


def test_atomic_writes_and_drift_detection(tmp_path):
    ledger = MemoryLedger(tmp_path / ".ethos-aegis" / "MEMORY.jsonl")
    store = StrictWriteDiscipline(tmp_path, memory_ledger=ledger)
    assert store.write_text("data/state.txt", "alpha").ok
    assert store.write_text("data/state.txt", "beta").ok
    assert len(ledger.list_events()) == 2
    assert DriftDetector(tmp_path, ledger=ledger).scan().verified == ["data/state.txt"]
    (tmp_path / "data" / "state.txt").write_text("changed")
    assert DriftDetector(tmp_path, ledger=ledger).scan().drifted == ["data/state.txt"]
    assert main(["--root", str(tmp_path), "--json"]) == 1
    assert not list((tmp_path / "data").glob(".aegis-*.tmp"))
    if os.name == "posix":
        assert ledger.path.stat().st_mode & 0o077 == 0


def test_dry_run_is_not_verified(tmp_path):
    store = StrictWriteDiscipline(tmp_path)
    report = store.write_text("x.txt", "data", dry_run=True)
    assert not report.ok and not report.verified_actions
    assert not (tmp_path / "x.txt").exists()


@pytest.mark.parametrize("path", ["../escape", "a/../escape", "a//b", "C:/Windows/file", "/tmp/file", "./file", ".git/config", "sub/.GiT/config", "NUL.txt", "bad. ", ".ethos-aegis/MEMORY.jsonl"])
def test_path_escape_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        StrictWriteDiscipline(tmp_path).write_text(path, "data")


def test_symlink_escape_rejected(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        StrictWriteDiscipline(tmp_path).write_text("link/escape.txt", "data")
    assert not (tmp_path.parent / "escape.txt").exists()


def test_unverified_missing_baseline_is_not_success(tmp_path):
    assert main(["--root", str(tmp_path)]) == 2


def test_write_size_limit(tmp_path):
    with pytest.raises(ValueError):
        StrictWriteDiscipline(tmp_path).write_text("large.txt", "x" * (8 * 1024 * 1024 + 1))

def test_symlinked_ledger_directory_is_rejected(tmp_path):
    external = tmp_path.parent / (tmp_path.name + "-outside")
    external.mkdir()
    (tmp_path / ".ethos-aegis").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        MemoryLedger(tmp_path / ".ethos-aegis" / "MEMORY.jsonl").append_verified(path="a", action="CREATE", before=None, after="fake")
    assert not (external / "MEMORY.jsonl").exists()
