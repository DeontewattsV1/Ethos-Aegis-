"""Run with ``python -m ethos_aegis.security_toolkit``."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .models import CATALOG, ToolId, ToolkitError
from .policy import AssessmentScope
from .runner import BoundedProcessRunner, SecurityToolkit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ethos Aegis: scoped security evidence and tool adapters")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="Show integration capabilities")
    demo = commands.add_parser("demo", help="Run an offline, synthetic walkthrough")
    demo.add_argument("--scenario", choices=["toolkit", "immune", "veriflow"], default="toolkit")
    for command in ("import", "run"):
        sub = commands.add_parser(command)
        sub.add_argument("tool", choices=[x.value for x in ToolId])
        sub.add_argument("target")
        sub.add_argument("--scope", required=True, type=Path)
        if command == "run":
            sub.add_argument("--execute", action="store_true", help="Execute; default only prints the plan")
            sub.add_argument("--executable", type=Path)
            sub.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            print(
                json.dumps(
                    {tool.value: {"feature": label, "support": support} for tool, (label, support) in CATALOG.items()},
                    indent=2,
                )
            )
            return 0
        if args.command == "demo":
            from .demo import run_demo

            run_demo(args.scenario)
            return 0
        with args.scope.open("rb") as handle:
            raw_scope = handle.read(65_537)
        if len(raw_scope) > 65_536:
            raise ToolkitError("Scope exceeds the byte budget.")
        scope = AssessmentScope.from_dict(json.loads(raw_scope))
        toolkit = SecurityToolkit(scope)
        tool = ToolId(args.tool)
        if args.command == "import":
            result = toolkit.import_report(tool, args.target).to_dict()
        elif not args.execute:
            result = asdict(toolkit.plan(tool, args.target))
        else:
            if args.executable is None:
                raise ToolkitError("Execution requires an explicit executable.")
            toolkit = SecurityToolkit(scope, BoundedProcessRunner(args.timeout))
            result = toolkit.execute(tool, args.target, args.executable).to_dict()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ToolkitError as exc:
        print(f"Ethos Aegis: {exc}", file=sys.stderr)
    except (OSError, ValueError, TypeError, AttributeError):
        print("Ethos Aegis: unable to read valid scope or tool evidence.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
