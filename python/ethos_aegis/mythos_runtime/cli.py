"""Read-only Mythos drift verification command."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .drift import DriftDetector
from .memory import MemoryLedger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Ethos Aegis Mythos drift verification")
    parser.add_argument("--root", default=".", help="Directory holding files that were verified")
    parser.add_argument("--ledger", default=".ethos-aegis/MEMORY.jsonl", help="Local receipt path under root")
    parser.add_argument("verify", nargs="?", default="verify", choices=("verify",))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve(strict=True)
    ledger = root / args.ledger
    if ledger.is_symlink() or not ledger.resolve().is_relative_to(root):
        parser.error("ledger path must remain under the selected project root")
    result = DriftDetector(root, ledger=MemoryLedger(ledger)).scan()
    payload = {"verified": result.verified, "drifted": result.drifted,
               "missing": result.missing, "unknown": result.unknown}
    if args.json:
        print(json.dumps(payload, sort_keys=True, indent=2))
    else:
        print(f"verified={len(result.verified)} drifted={len(result.drifted)} missing={len(result.missing)}")
    if not ledger.exists() or not result.verified and not result.drifted and not result.missing:
        return 2  # No baseline, not a verified clean state.
    return 1 if result.drifted or result.missing else 0

if __name__ == "__main__":
    raise SystemExit(main())
