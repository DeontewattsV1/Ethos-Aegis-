# AEGIS Private Shield — Constitutional Security Model v0.1

> **North-star invariant:** Compromise should become a contained event, not a system-wide event.

AEGIS Private Shield does not assume an AI model can be made trustworthy enough to possess every secret or exercise ambient authority. It assumes that any model, agent, micro-agent, prompt, tool, plugin, file, dependency, or retrieved document may eventually behave incorrectly or maliciously.

The system therefore trusts the boundary rather than the intelligence inside the boundary.

## Constitutional invariants

1. **Default deny.** No sensitive operation is permitted unless every required predicate is satisfied.
2. **Secret non-possession.** AI principals should use brokered credentials through approved operations rather than receive raw long-lived secrets.
3. **Capability boundedness.** Authority is represented as narrow, expiring capability grants, not ambient credentials.
4. **Read != reveal != execute != modify.** These are separate capabilities.
5. **Micro-agent isolation.** Shared project membership does not imply shared authority.
6. **Complete mediation.** Protected operations pass through the reference monitor.
7. **Egress mediation.** Reading private data does not imply permission to export it.
8. **Untrusted input has no authority.** Retrieved content cannot grant itself permissions.
9. **No confused deputy.** Effective authority is the intersection of caller, tool, and project authority.
10. **Temporal least privilege.** Grants expire with the task/session.
11. **Risk monotonicity.** Authority contracts as uncertainty increases.
12. **Production mutation requires a higher-trust gate.** High-impact actions can require explicit human approval.
13. **Evidence completeness.** Authorization attempts produce tamper-evident receipts, including denied attempts.
14. **Revocability and fail-closed behavior.** Missing or invalid predicates result in denial.
15. **Private-source non-exfiltration.** Source visibility and export rights remain independent.
16. **Sandboxed execution.** Untrusted execution belongs in constrained environments rather than the host.
17. **Artifact quarantine.** Untrusted artifacts remain untrusted until policy and scanner acceptance.
18. **Communication-channel control.** Isolation must account for shared writable/readable state, not only explicit chat channels.

## Core authorization equation

For a requested action `a`:

```text
Permit(a) = I ∧ P ∧ R ∧ C ∧ E ∧ T
```

where:

```text
I = verified identity
P = project policy authorization
R = authorized resource
C = active capability grant
E = permitted execution environment
T = valid time-bounded authority
```

AEGIS v0.1 also evaluates data flow:

```text
Permit(a, flow)
  = Permit(a)
  ∧ FlowPolicy(source, destination, data_classification)
```

and prevents confused-deputy escalation:

```text
EffectiveAuthority
  = AgentAuthority
  ∩ ToolAuthority
  ∩ ProjectPolicy
  ∩ Session/RiskEnvelope
```

## Risk-adaptive authority

The implementation represents authority as a set of capability grants. Each grant has a maximum tolerated risk value. If the current uncertainty exceeds that ceiling, the grant is no longer active.

```text
R(t+1) > R(t)  =>  C(t+1) ⊆ C(t)
```

unless a trusted policy/human action explicitly grants new authority.

This is stronger than scaling a single numeric privilege score because indivisible dangerous powers are removed as discrete capabilities.

## What v0.1 makes testable

The Python reference implementation under `python/ethos_aegis/private_shield/` verifies these properties:

- unverified identities are denied;
- expired grants are denied;
- higher risk removes high-impact capabilities before lower-risk read capabilities;
- a high-authority tool cannot be used as a confused deputy by a lower-authority agent;
- private source read access does not imply export permission;
- explicit approval gates produce `REQUIRE_APPROVAL` instead of silently executing;
- denied attempts still generate evidence receipts;
- alteration of a receipt or its chain is detected.

## v0.1 evidence model

The reference implementation uses SHA-256 hashes and HMAC-SHA256 signatures because the package currently has zero mandatory third-party dependencies. Production deployments should move the signing key behind KMS/HSM and may use asymmetric signatures such as Ed25519 for externally verifiable receipts.

No raw prompt, secret, source payload, or tool output needs to be placed in the audit chain. The receipt records hashes, identity/action metadata, capability identifiers, risk, decision, and the preceding receipt hash.

## Next hardening layers

The reference monitor is intentionally narrow. Subsequent layers should add opaque secret references and leased credentials, source classification/redaction, malware quarantine, sandbox/network/filesystem policies, DLP/secret detection, capability revocation, workload identity, MCP/tool mediation, and production-grade append-only evidence storage.
