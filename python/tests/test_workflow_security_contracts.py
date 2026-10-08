"""Prevent regressions in release credentials and required CI security coverage.

These checks use the raw workflow text so they need no optional YAML dependency.
They enforce narrow, critical invariants rather than GitHub Actions' full schema.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_publish_token_only_exists_at_publish_step() -> None:
    """Only the release-triggered SDK publish step can access the package token."""
    workflow = _workflow("release-packages.yml")
    npm_job = workflow.split("  publish-npm:\n", 1)[1].split("\n  attach-assets:\n", 1)[0]
    before_publish, publish_step = npm_job.split(
        "      - name: Publish to GitHub Packages\n", 1
    )
    assert "secrets.NPM_TOKEN" not in npm_job
    assert "NPM_TOKEN:" not in npm_job
    assert "NODE_AUTH_TOKEN:" not in before_publish
    assert "secrets.GITHUB_TOKEN" not in before_publish
    assert "working-directory: sdk/node" in before_publish
    assert "if: github.event_name == 'release'" in before_publish
    assert "registry-url: https://npm.pkg.github.com" in before_publish
    assert 'scope: "@deontewattsv1"' in before_publish
    assert "NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in publish_step
    assert "run: npm publish" in publish_step


def test_root_node_scaffold_is_not_the_published_sdk() -> None:
    """The publish job must target the SDK, never the root docs scaffold."""
    import json

    scaffold = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert scaffold["private"] is True
    assert scaffold["name"] == "living-docs-template"
    workflow = _workflow("release-packages.yml")
    npm_job = workflow.split("  publish-npm:\n", 1)[1]
    assert "working-directory: sdk/node" in npm_job
    assert "registry-url: https://npm.pkg.github.com" in npm_job

def test_codeql_push_and_pr_cover_root_and_scripts() -> None:
    workflow = _workflow("codeql.yml")
    triggers = workflow.split("\non:\n", 1)[1].split("\nconcurrency:\n", 1)[0]
    assert "push:" in triggers
    assert "pull_request:" in triggers
    assert "paths:" not in triggers
    assert "javascript-typescript" in workflow
    assert "python" in workflow
    assert "language: actions" in workflow


def test_security_scans_do_not_suppress_failures() -> None:
    workflow = _workflow("ci.yml")
    scan = workflow.split("\n  security:\n", 1)[1].split("\n  sandbox:\n", 1)[0]
    assert "bandit -r ethos_aegis/" in scan
    assert "pip-audit" in scan
    assert '"setuptools>=83.0.0"' in scan
    assert "|| true" not in scan


def test_pipeline_report_fails_closed_on_skip_failure_or_cancellation() -> None:
    workflow = _workflow("ci.yml")
    report = workflow.split("\n  report:\n", 1)[1]
    for gate in (
        "LINT_RESULT", "PYTHON_RESULT", "MACOS_RESULT",
        "WINDOWS_PATHS_RESULT", "WINDOWS_RESULT",
        "SECURITY_RESULT", "SANDBOX_RESULT",
    ):
        assert gate in report
    assert 'if [ "${outcome}" != "success" ]; then' in report
