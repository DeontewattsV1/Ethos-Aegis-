from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .types import TargetContext


class TargetIntakeScaffold:
    """Normalizes a local repository slice into a compact analysis context."""

    BUILD_FILE_CANDIDATES = (
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
    )

    def from_path(self, root: str | Path, *, name: str | None = None) -> TargetContext:
        path = Path(root).resolve()
        build_files = [candidate for candidate in self.BUILD_FILE_CANDIDATES if (path / candidate).exists()]
        languages = self._detect_languages(path)
        test_commands = self._infer_test_commands(build_files)
        notes: List[str] = []
        if (path / "tests").exists():
            notes.append("tests directory present")
        if (path / ".github").exists():
            notes.append("github automation present")
        if (path / ".gitlab-ci.yml").exists():
            notes.append("gitlab ci present")
        return TargetContext(
            name=name or path.name,
            root=path,
            languages=languages,
            build_files=build_files,
            test_commands=test_commands,
            notes=notes,
            metadata={"file_count_hint": self._count_source_files(path)},
        )

    def _detect_languages(self, root: Path) -> List[str]:
        suffix_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cc": "cpp",
            ".cpp": "cpp",
            ".c": "c",
            ".mjs": "javascript",
        }
        seen = set()
        for file_path in root.rglob("*"):
            if file_path.is_file() and file_path.suffix in suffix_map:
                seen.add(suffix_map[file_path.suffix])
        return sorted(seen)

    def _infer_test_commands(self, build_files: Iterable[str]) -> List[str]:
        commands: List[str] = []
        build_files = set(build_files)
        if "pyproject.toml" in build_files or "requirements.txt" in build_files:
            commands.append("python -m pytest -q")
        if "package.json" in build_files:
            commands.append("npm test")
        if "Cargo.toml" in build_files:
            commands.append("cargo test")
        if "go.mod" in build_files:
            commands.append("go test ./...")
        if "Makefile" in build_files:
            commands.append("make test")
        return commands

    def _count_source_files(self, root: Path) -> int:
        count = 0
        for file_path in root.rglob("*"):
            if file_path.is_file() and file_path.suffix in {".py", ".js", ".ts", ".rs", ".go", ".c", ".cc", ".cpp"}:
                count += 1
        return count
