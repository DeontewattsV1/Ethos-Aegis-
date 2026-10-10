# Ethos Aegis SDKs

The archive's four clients are now placed under the current repository layout and attributed to Ethos Aegis. Install from source; no registry publication is implied.

| Client | Transport | Verification status | Main entry |
|---|---|---|---|
| Python | Embedded / HTTP(S) | Local embedded and guard-boundary tests | `sdk/python/ethos_aegis_sdk/client.py` |
| Node / TypeScript | Python subprocess / HTTP(S) | Local subprocess and guard-boundary tests | `sdk/node/src/index.js` |
| Go | Python subprocess / HTTP(S) | Archive reference; build/runtime not validated here | `sdk/go/aegis/client.go` |
| Rust | Python subprocess / loopback HTTP | Archive reference; build/runtime not validated here; no TLS | `sdk/rust/src/lib.rs` |

Guards require explicit clearance rather than only `condemned == false`. Python and Node pass returned purification to the model and reject sanitized HTTP verdicts without purified content. Rust conservatively blocks sanitized verdicts. These clients screen inputs; they do not prove an LLM output is safe or authorize a tool call.

## Python

```bash
python -m pip install -e ./python
python -m pip install -e ./sdk/python
```

```python
from ethos_aegis_sdk import AegisClient

client = AegisClient(auto_nourish=False)
result = client.guard("Explain a computer", llm_fn=lambda text: "Your model response")
print(result.was_blocked)
```

HTTP mode requires an independently deployed and authenticated server. The wrapper requires HTTPS for bearer credentials outside loopback, bounds response size and does not follow redirects. Installation deploys no server.

## Node / TypeScript

```javascript
import { AegisClient } from "./sdk/node/src/index.mjs";

const client = new AegisClient({repoRoot: "/absolute/path/to/Ethos-Aegis"});
const result = await client.guard({
  message: "Explain a computer",
  llmFn: async (text) => "Your model response"
});
console.log(result.blocked);
```

CommonJS entry: `sdk/node/src/index.js`. Declarations: `sdk/node/types/index.d.ts`. Subprocess calls require Python 3.10+ and the **separate Ethos Aegis Python core**, and are synchronous despite the async API. The middleware factory implements an Express-compatible request shape.

**For a cloned repository**, pass `repoRoot` pointing to that clone, as above. The core lives in `python/ethos_aegis` and is not bundled in the Node SDK.

**For a separately installed Node package**, install the Python core into the `pythonBin` interpreter independently (for example, `python -m pip install /path/to/Ethos-Aegis-/python`) and omit `repoRoot`; the SDK now uses the installed Python distribution instead of deriving a bogus source path under `node_modules`. If the core is absent, adjudication fails with a descriptive `AegisTransportError` rather than assuming an unrelated checkout. Use `new AegisClient({transport: "http", serverUrl: "https://your-authorized-server.example/v1/adjudicate"})` only with a separately deployed and verified service; installing the SDK or GHCR Node image **does not deploy an HTTP server**.

The npm distribution configured at `sdk/node/package.json` is `@deontewattsv1/ethos-aegis-sdk` on GitHub Packages and is published only from an approved GitHub Release workflow; registry availability and anonymous access require separate verification. Do not claim the npm package includes the Python core or that the container exposes a functional API.

## Reference clients

Go and Rust remain source references for follow-up validation. They are not designated production-ready. Rust rejects HTTPS rather than silently sending it over plaintext; its reference HTTP transport is loopback only. Validate builds, TLS, budgets and process boundaries before application deployment.

## Test from source

```bash
PYTHONPATH=python:sdk/python python -m pytest sdk/python/tests -q
node --test sdk/node/tests/*.test.js
# With separately installed toolchains:
# (cd sdk/go && go test ./...)
# (cd sdk/rust && cargo test)
```

Each SDK retains the archive MIT license. See [archive provenance](../docs/provenance/archive-integration.json) and [third-party notices](../THIRD_PARTY_NOTICES.md).
