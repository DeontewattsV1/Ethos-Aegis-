"""Explicit external CLI adapters; nothing is downloaded, installed, or run at import."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path

from .models import SecurityReport, ToolId, ToolkitError, ToolPlan
from .parsers import MAX_BYTES, normalize, read_evidence
from .policy import AssessmentScope


class BoundedProcessRunner:
    """Shell-free argv with bounded output/time. Not OS or network isolation."""

    def __init__(self, timeout: float = 60.0, max_bytes: int = MAX_BYTES) -> None:
        if not 0 < timeout <= 300 or not 0 < max_bytes <= MAX_BYTES:
            raise ToolkitError("Invalid execution budget.")
        self.timeout = timeout
        self.max_bytes = max_bytes

    def run(self, argv: list[str], cwd: Path) -> bytes:
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "WINDIR", "JAVA_HOME", "LANG"}
        }
        env["HOME"] = str(cwd)
        env["USERPROFILE"] = str(cwd)
        env["TMPDIR"] = str(cwd)
        env["TEMP"] = str(cwd)
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=os.name == "posix",
            )
        except OSError:
            raise ToolkitError("Unable to start the configured tool.") from None
        chunks: list[bytes] = []
        overflow = threading.Event()

        def drain() -> None:
            total = 0
            while process.stdout is not None:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_bytes:
                    overflow.set()
                    break
                chunks.append(chunk)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + self.timeout
        try:
            while process.poll() is None:
                if overflow.is_set():
                    raise ToolkitError("Tool output exceeds the byte budget.")
                if time.monotonic() >= deadline:
                    raise ToolkitError("Tool execution exceeded its time budget.")
                time.sleep(0.02)
            reader.join(timeout=max(0, deadline - time.monotonic()))
            if reader.is_alive():
                raise ToolkitError("Tool output did not finish within the time budget.")
            if overflow.is_set():
                raise ToolkitError("Tool output exceeds the byte budget.")
            if process.returncode != 0:
                raise ToolkitError("Tool execution failed; raw logs are withheld.")
            return b"".join(chunks)
        finally:
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            elif process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()


class SecurityToolkit:
    def __init__(self, scope: AssessmentScope, runner: BoundedProcessRunner | None = None) -> None:
        self.scope = scope
        self.runner = runner or BoundedProcessRunner()

    def import_report(self, tool: ToolId, source: str | Path) -> SecurityReport:
        self.scope.check(tool)
        return normalize(tool, read_evidence(source, self.scope), self.scope)

    def plan(self, tool: ToolId, target: str) -> ToolPlan:
        self.scope.check(tool)
        if tool == ToolId.SHERLOCK:
            self.scope.username(target)
            network = True
            description = "Check the authorized username only on explicitly selected Sherlock sites."
        elif tool in {ToolId.TRUFFLEHOG, ToolId.GHIDRA}:
            target = str(self.scope.local_path(target, directory=tool == ToolId.TRUFFLEHOG))
            network = False
            description = (
                "Scan a local filesystem with credential verification disabled."
                if tool == ToolId.TRUFFLEHOG
                else "Analyze a local binary in a disposable Ghidra project."
            )
        else:
            raise ToolkitError("This integration supports evidence import only.")
        return ToolPlan(tool, hashlib.sha256(target.encode()).hexdigest(), network, description)

    def execute(self, tool: ToolId, target: str, executable: str | Path) -> SecurityReport:
        plan = self.plan(tool, target)
        self.scope.check(tool, execute=True, network=plan.network_requested)
        executable = Path(executable)
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise ToolkitError("An absolute path to an installed executable is required.")
        with tempfile.TemporaryDirectory(prefix="ethos-aegis-") as temporary:
            work = Path(temporary)
            if tool == ToolId.TRUFFLEHOG:
                path = self.scope.local_path(target, directory=True)
                # Reject links before handing the tree to a third-party scanner.
                # Operators must keep the scan tree immutable during execution.
                for index, child in enumerate(path.rglob("*")):
                    if index >= 100_000:
                        raise ToolkitError("Scan tree exceeds the file budget.")
                    if child.is_symlink():
                        raise ToolkitError("Linked scan-tree entries are not supported.")
                # Git history remains an import workflow; the local runner scans filesystem contents only.
                argv = [str(executable), "filesystem", str(path), "--json", "--no-verification", "--no-update"]
                data = self.runner.run(argv, work)
            elif tool == ToolId.SHERLOCK:
                self.scope.username(target)
                argv = [str(executable), target, "--csv", "--folderoutput", str(work), "--timeout", "10", "--local"]
                for site in self.scope.sites:
                    argv.extend(["--site", site])
                self.runner.run(argv, work)
                source = work / f"{target}.csv"
                with source.open("rb") as handle:
                    data = handle.read(MAX_BYTES + 1)
            elif tool == ToolId.GHIDRA:
                path = self.scope.local_path(target)
                scripts = Path(__file__).parent / "ghidra_scripts"
                summary = work / "summary.json"
                argv = [
                    str(executable),
                    str(work),
                    "EthosAegis",
                    "-import",
                    str(path),
                    "-scriptPath",
                    str(scripts),
                    "-postScript",
                    "EthosAegisSummary.java",
                    str(summary),
                    "-analysisTimeoutPerFile",
                    "45",
                    "-max-cpu",
                    "1",
                    "-deleteProject",
                ]
                self.runner.run(argv, work)
                with summary.open("rb") as handle:
                    data = handle.read(MAX_BYTES + 1)
            else:
                raise ToolkitError("This integration supports evidence import only.")
            # Scope expiry is checked again before accepting results.
            return normalize(tool, data, self.scope, mode="execution")
