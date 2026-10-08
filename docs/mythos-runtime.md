# Mythos Runtime — VeriFlow production assurance bridge

**Status:** Mythos is automatically connected to VeriFlow whenever a `MythosVeriflowRuntime` is supplied to `VeriflowImmuneSystem`. The default non-production API remains backward compatible; production mode is fail-closed and requires an operator-issued execution grant.

## Production controls

- **Independent authorization:** the trusted control plane owns `ExecutionGrantSigner`; runtime code receives only `ExecutionGrantVerifier`. Grants are short-lived and bound to subject, purposes, actions, resource IDs, CKAN host, execution environment, target environment, and source revision.
- **Trusted environment enforcement:** `TrustedEnvironment` is fixed at runtime construction and compared exactly against the signed grant. Production CKAN endpoints must use credential-free HTTPS.
- **Automatic execution mediation:** capability probes, resource refresh/ingestion, and question answering call Mythos automatically before execution. Missing, expired, wrong-purpose, wrong-resource, wrong-host, wrong-environment, or wrong-revision grants fail before network work.
- **Authenticated state:** persisted VeriFlow state is HMAC-authenticated and bound to the trusted environment. Unsigned legacy state is rejected in production mode.
- **Retention:** `RetentionPolicy` bounds evidence by age/count and resource state by TTL/count/bytes. Raw dataset rows are not persisted by default in production.
- **Durability:** state/evidence writes use temporary files, fsync, atomic replacement, private POSIX modes, symlink rejection, bounded sizes, and fail-closed writer locks.
- **Evidence:** the assurance ledger stores bounded metadata and hashes, not raw questions or dataset rows.

## Recommended runtime posture

Startup probing remains enabled. `fingerprint_mode="auto"` is now the default: CKAN Datastore resources use a lightweight row signature automatically, while other resources fall back to metadata fingerprints.

## Example

```python
from ethos_aegis.mythos_runtime import (
    ExecutionGrantSigner, ExecutionGrantVerifier, MythosVeriflowRuntime,
    RetentionPolicy, TrustedEnvironment,
)
from ethos_aegis.veriflow import CKANClient, VeriflowImmuneSystem

# Source these from trusted secret storage. Keep the signer outside model/tool code.
authorization_key = b"<32+ bytes>"
persistence_key = b"<different 32+ bytes>"

environment = TrustedEnvironment(
    execution_environment="service-prod-us-west",
    target_environment="ckan-production",
    ckan_base_url="https://data.example.gov",
    source_revision="<deployed git SHA>",
)
token = ExecutionGrantSigner(authorization_key).issue(
    subject="service://veriflow",
    purposes=("capability_probe", "dataset_refresh", "question_answer"),
    actions=("veriflow.probe", "veriflow.refresh", "veriflow.answer"),
    resources=("resource-id",),
    environment=environment,
    ttl_seconds=300,
)
bridge = MythosVeriflowRuntime(
    environment=environment,
    grant_verifier=ExecutionGrantVerifier(authorization_key),
    persistence_key=persistence_key,
    state_dir="/var/lib/ethos-aegis",
    retention=RetentionPolicy(),
)
immune = VeriflowImmuneSystem(
    CKANClient(environment.ckan_base_url),
    sample_resource_id="resource-id",
    mythos_runtime=bridge,
    execution_grant=token,
)
answer = immune.answer_question("resource-id", "What changed?")
```

Rotate grants with `immune.set_execution_grant(new_token)` before expiry. The HMAC format is a reference implementation for a single trust domain; production deployments needing centralized revocation or asymmetric verification should put issuance/signing behind KMS/HSM or an external authorization service.

Production mode rejects unsigned legacy VeriFlow state. Migrate it explicitly or use an empty production state directory. Retention is a deletion policy, not proof that external backups or exported copies have been removed.

`BudgetMeter`, `StrictWriteDiscipline`, `MemoryLedger`, and `DriftDetector` remain available for local explicit workflows.
