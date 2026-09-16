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
19. **Path semantic invariance.** A resource path must have one policy meaning regardless of Linux, macOS, or Windows host semantics.
20. **Opaque credential delegation.** Agent-visible authority to use a secret is a short-lived opaque lease, never the secret material itself.
21. **Tool execution mediation.** A registered MCP/tool handler must not execute until caller, tool, project, environment, risk, and flow authority intersect.

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

AEGIS also evaluates data flow:

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

## Cross-platform path boundary

AEGIS policy matching uses a canonical POSIX-like virtual namespace even when execution occurs on Windows or macOS. Backslashes are normalized to `/`, while host-specific or ambiguous path forms fail closed before authorization.

The reference implementation rejects parent traversal, absolute paths, Windows drive paths, UNC paths, NTFS alternate-data-stream syntax, Windows reserved device names, trailing-dot/space aliases, NUL bytes, and untrusted glob syntax in requested resource paths.

```text
PolicyMeaning(path, Linux)
  = PolicyMeaning(path, macOS)
  = PolicyMeaning(path, Windows)
```

for paths admitted into the AEGIS virtual namespace.

## Secret non-possession boundary

`SecretBroker` is the only reference component that stores raw secret material. An authorized agent receives a short-lived `SecretLease` containing an opaque lease identifier, secret reference, purpose, expiration, and use limit. It does not contain credential bytes.

```text
agent
  -> secret.use authorization
  -> opaque lease_id
  -> trusted adapter
  -> broker resolves credential internally
  -> operation
  -> lease consumed/revoked
  -> evidence receipt
```

The reference broker constrains lease TTL and use count, supports explicit revocation, consumes uses even when the trusted adapter fails, and blocks direct reflection of raw credential material in an adapter result. The reflection check is a narrow reference containment check, not a replacement for the future full DLP/egress layer.

## MCP mediation boundary

`MCPMediator` registers trusted handlers behind a `mcp://` resource and `tool://` identity. A handler is not invoked until policy evaluation succeeds for the caller and tool together.

```text
MCPExecute
  => AgentAuthority
   ∩ ToolAuthority
   ∩ ProjectPolicy
   ∩ Session/RiskEnvelope
```

Denied calls produce an evidence receipt but never call the handler. Allowed calls hash arguments and results into the receipt rather than storing their raw contents.

The integration suite also composes both boundaries: an agent passes only an opaque secret lease ID into an authorized MCP call, and the trusted MCP adapter resolves the credential through the broker. Model-facing input and output never contain the raw secret.

## Cross-platform CI evidence

The focused Private Shield suite runs as dedicated GitHub Actions compatibility gates on `macos-latest` and `windows-latest`, while the existing Linux Python matrix remains authoritative for the full package. Each non-Linux gate uploads a JUnit artifact so cross-platform conformance is inspectable from workflow history.

## Evidence model

The reference implementation uses SHA-256 hashes and HMAC-SHA256 signatures because the package currently has zero mandatory third-party dependencies. Production deployments should move the signing key behind KMS/HSM and may use asymmetric signatures such as Ed25519 for externally verifiable receipts.

No raw prompt, secret, source payload, or tool output needs to be placed in the audit chain. The receipt records hashes, identity/action metadata, capability identifiers, risk, decision, and the preceding receipt hash.

## Next hardening layers

The next boundary should replace the in-memory secret backend with pluggable Vault/cloud secret-manager/KMS adapters, add capability revocation propagation and workload identity, mediate real MCP transports rather than in-process handlers, add source classification/redaction and DLP, and bind sandbox/network/filesystem enforcement to the same signed evidence stream.
