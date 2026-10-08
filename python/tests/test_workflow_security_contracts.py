"""Prevent regressions in release credentials and required CI security coverage.

These checks use the raw workflow text so they need no optional YAML dependency.
They enforce narrow, critical invariants rather than GitHub Actions' full schema.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_publish_token_only_exists_at_publish_step() -> None:
    workflow = _workflow("release-packages.yml")
    npm_job = workflow.split("  publish-npm:\n", 1)[1].split("  attach-assets:\n", 1)[0]
    before_publish, publish_step = npm_job.split("      - name: Publish to npm\n", 1)
    assert "secrets.NPM_TOKEN" not in before_publish
    assert "NPM_TOKEN:" not in before_publish
    assert "secrets.NPM_TOKEN" in publish_step
    assert 'if [ -z "${NODE_AUTH_TOKEN}" ]; then' in publish_step


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
