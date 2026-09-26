from datetime import datetime, timedelta, timezone

import pytest

from ethos_aegis.private_shield import (
    ActionRequest,
    CapabilityGrant,
    Decision,
    PathPolicyError,
    PolicyEngine,
    ProjectPolicy,
    canonicalize_resource_path,
)

NOW = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)


def _grant() -> CapabilityGrant:
    return CapabilityGrant(
        capability_id="cap-cross-platform-read",
        subject="agent://coder-17",
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )


def _policy() -> ProjectPolicy:
    return ProjectPolicy(
        resource="repo://project",
        actions=frozenset({"source.read"}),
        scopes=("src/**",),
    )


def test_windows_and_posix_separators_map_to_same_policy_namespace() -> None:
    assert canonicalize_resource_path(r"src\auth\session.py") == "src/auth/session.py"
    assert canonicalize_resource_path("src/auth/session.py") == "src/auth/session.py"

    decision = PolicyEngine().evaluate(
        ActionRequest(
            subject="agent://coder-17",
            action="source.read",
            resource="repo://project",
            path=r"src\auth\session.py",
        ),
        identity_verified=True,
        project_policy=_policy(),
        agent_grants=[_grant()],
        now=NOW,
    )
    assert decision.decision is Decision.ALLOW


@pytest.mark.parametrize(
    "path",
    [
        "../secrets/key.txt",
        "src/../../secrets/key.txt",
        "/etc/passwd",
        r"C:\Windows\System32\config\SAM",
        r"\\server\share\secret.txt",
        "src/file.txt:alternate-stream",
        "src/CON",
        "src/NUL.txt",
        "src/name. ",
    ],
)
def test_ambiguous_or_host_specific_paths_are_rejected(path: str) -> None:
    with pytest.raises(PathPolicyError):
        canonicalize_resource_path(path)


def test_invalid_path_fails_closed_in_policy_engine() -> None:
    decision = PolicyEngine().evaluate(
        ActionRequest(
            subject="agent://coder-17",
            action="source.read",
            resource="repo://project",
            path="src/../../secrets/key.txt",
        ),
        identity_verified=True,
        project_policy=_policy(),
        agent_grants=[_grant()],
        now=NOW,
    )
    assert decision.decision is Decision.DENY
    assert decision.reasons == ("scope_outside_project_policy",)


def test_redundant_separators_and_current_directory_are_canonicalized() -> None:
    assert canonicalize_resource_path("src//auth/./session.py") == "src/auth/session.py"
