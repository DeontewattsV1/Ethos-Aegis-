"""Regression tests: policy globs must not widen authority across path segments.

The project and delegated capability gates must each deny an unexpected nested
path. These tests exercise default-deny evaluation, not just a matcher helper.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ethos_aegis.private_shield import (
    ActionRequest,
    CapabilityGrant,
    Decision,
    PolicyEngine,
    ProjectPolicy,
)
from ethos_aegis.private_shield.policy import _scope_allows

_NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("src/*.py", "src/a.py", True),
        ("src/*.py", "src/private/secret.py", False),
        ("src/?.py", "src/a.py", True),
        ("src/?.py", "src/private/a.py", False),
        ("src/[ab].py", "src/b.py", True),
        ("src/[ab].py", "src/private/a.py", False),
        ("src/**/audit.py", "src/audit.py", True),
        ("src/**/audit.py", "src/nested/deeper/audit.py", True),
        ("src/**", "src", True),
        ("src/**", "src/private/secret.py", True),
        ("**/*.py", "root.py", True),
        ("*", "any/depth/allowed.py", True),
        ("src/*.py", "../src/a.py", False),
        ("src/*.py", r"C:\src\a.py", False),
        ("src/*.py", "src/private/../a.py", False),
    ],
)
def test_path_scope_segment_semantics(pattern: str, path: str, expected: bool) -> None:
    assert _scope_allows(path, (pattern,)) is expected


@pytest.mark.parametrize(
    ("project_scope", "grant_scope", "expected_reason"),
    [
        ("src/*.py", "src/**", "scope_outside_project_policy"),
        ("src/**", "src/*.py", "no_active_agent_capability"),
    ],
)
def test_project_and_agent_scopes_independently_deny_nested_access(
    project_scope: str, grant_scope: str, expected_reason: str
) -> None:
    request = ActionRequest(
        subject="agent://tester",
        action="source.read",
        resource="repo://project",
        path="src/private/secret.py",
    )
    project = ProjectPolicy(
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=(project_scope,),
    )
    grant = CapabilityGrant(
        capability_id="read-only",
        subject="agent://tester",
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=(grant_scope,),
        issued_at=_NOW - timedelta(seconds=30),
        expires_at=_NOW + timedelta(minutes=10),
    )
    result = PolicyEngine().evaluate(
        request,
        identity_verified=True,
        project_policy=project,
        agent_grants=(grant,),
        now=_NOW,
    )
    assert result.decision is Decision.DENY
    assert expected_reason in result.reasons


def test_nested_access_requires_explicit_recursive_grant_on_both_sides() -> None:
    request = ActionRequest("agent://tester", "source.read", "repo://project", path="src/private/secret.py")
    project = ProjectPolicy(
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
    )
    grant = CapabilityGrant(
        capability_id="recursive-read",
        subject="agent://tester",
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
        issued_at=_NOW - timedelta(seconds=30),
        expires_at=_NOW + timedelta(minutes=10),
    )
    result = PolicyEngine().evaluate(
        request, identity_verified=True, project_policy=project, agent_grants=[grant], now=_NOW
    )
    assert result.decision is Decision.ALLOW
