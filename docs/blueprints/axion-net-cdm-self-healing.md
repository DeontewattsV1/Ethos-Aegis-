# Axion-Net CDM Self-Healing Mesh

Ethos Aegis uses a weakly coupled governance mesh: language fields remain sovereign, but every boundary crossing is mediated by schema version negotiation, trace identity, token pressure, and shared circuit-breaker state.

## Operating contract

- Every payload carries `agentId`, `traceId`, `schemaVersion`, `compatibleVersions`, and a CDM signature.
- The CDM signature must be stable and weakly interacting before the message can cross a brane boundary.
- Token buckets are keyed by agent and target field, so pressure follows the agent across replicas.
- Circuit breakers are keyed by agent and target field, so a fatal signal detected on one replica protects the whole lattice.
- Schema negotiation happens before semantic execution; incompatible payloads fail closed.

## Six-stage adjudication mapping

| Stage | Code surface | Purpose |
|---|---|---|
| 1. Innate response | `AegisMesh.scan` / `VanguardProbe` | Fast structural clearance |
| 2. Structural purification | `SchemaRegistry.negotiate` | Version bridge and schema safety |
| 3. Adaptive response | `AegisMesh.scan` / `LogosScythe` | CDM stability and weak coupling |
| 4. Memory matching | `stableHash` / `fingerprint` | Deterministic lineage fingerprint |
| 5. Resource monitoring | `NeuroStressBuffer` | Shared token pressure and entropy control |
| 6. Terminal enforcement | `SharedCircuitBreaker` | Global fail-closed containment |

## Upgrade path

The in-memory store is intentionally an adapter. Production Redis can implement the same `AtomicStateStore` contract with Lua-backed atomic mutations, preserving the test surface while moving shared state out of a single process.

```ts
export interface AtomicStateStore {
  mutate<TState extends object, TResult>(
    key: string,
    initialState: TState,
    mutation: (state: TState) => { state: TState; result: TResult }
  ): Promise<TResult>;
}
```

That keeps the architecture portable: local tests stay deterministic, CI stays fast, and distributed deployments can swap the store without rewriting the governance logic.
