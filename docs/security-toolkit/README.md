# Ethos Aegis Security Toolkit

Five independent tools feed one typed evidence contract. Ethos Aegis adds scope checks, private report normalization, provenance, bounded execution and a bridge into its existing defensive review scaffolds.

| Tool | Integration shipped here | Input | Execution |
|---|---|---|---|
| [TruffleHog](https://github.com/trufflesecurity/trufflehog) | Credential observations | Upstream JSONL | Local filesystem scan, verification and updates disabled |
| [Sherlock](https://github.com/sherlock-project/sherlock) | Possible username matches | Upstream CSV | Explicit username/site list, network grant required |
| [Ghidra](https://github.com/NationalSecurityAgency/ghidra) | Static binary inventory | Ethos Aegis summary JSON | Headless local analysis in a disposable project |
| [mitmproxy](https://github.com/mitmproxy/mitmproxy) | Application egress observations | HAR / sanitized flow JSONL | Import only; addon for an operator-started test session |
| [ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder) | Owned wireless inventory | Ethos Aegis summary JSONL | Import only; hardware collection remains operator controlled |

No upstream source, executable, Java runtime or firmware is installed or bundled automatically. Pin tools separately and verify releases using upstream signatures/checksums.

## Start locally

From the repository root:

```bash
python -m pip install -e ./python
python -m ethos_aegis.security_toolkit catalog
python -m ethos_aegis.security_toolkit demo --scenario toolkit
```

The installed `aegis-security` command is equivalent. The demo uses synthetic local records and starts no external scanner, proxy or radio.

## Establish a scope

Copy [scope.example.json](scope.example.json) and replace its absolute paths, authorization reference, expiry and targets. Tools and targets must be listed; execution and network default to false.

The scope file is an **operator attestation**, not authenticated identity or a signed capability. Protect it with filesystem permissions and keep it outside untrusted repositories. A hosted control plane must supply this configuration after authentication and independent authorization. Never accept it from a model, tool output or unauthenticated caller.

```bash
# Import private evidence without starting a tool:
aegis-security import trufflehog /absolute/authorized/reports/secrets.jsonl --scope scope.json
# Print a plan:
aegis-security run trufflehog /absolute/authorized/repository --scope scope.json
# With allow_execution=true in the protected scope:
aegis-security run trufflehog /absolute/authorized/repository \
  --scope scope.json --execute --executable /absolute/bin/trufflehog
```

Canonical paths are checked by directory ancestry, so a sibling sharing a prefix is not authorized. TruffleHog trees with links are rejected. Keep scan trees immutable during execution; validation does not prevent concurrent adversarial filesystem changes.

## TruffleHog: filesystem and Git history

The runner invokes `filesystem` with `--json --no-verification --no-update`. It never verifies credentials against a provider. For history, run an independently authorized upstream local Git scan and import JSONL:

```bash
trufflehog git file:///absolute/authorized/repository \
  --json --no-verification --no-update > /absolute/authorized/reports/history.jsonl
aegis-security import trufflehog /absolute/authorized/reports/history.jsonl --scope scope.json
```

Raw upstream JSONL may contain credentials; keep it private. Exports retain numeric detector IDs and tool claims, and discard Raw, RawV2, Redacted, ExtraData, filenames and arbitrary detector names. A tool's Verified=true remains a claim, not an independently verified finding.

## Sherlock: exact username and selected sites

Set an authorized username, `sites: ["GitHub"]`, `allow_execution: true` and `allow_network: true`:

```bash
aegis-security run sherlock owned_username --scope scope.json \
  --execute --executable /absolute/bin/sherlock
```

The runner uses the installed local catalog with `--local` and repeats `--site` for the explicit list. No arbitrary flags, proxy, remote catalog or browser opening is exposed. The installed Sherlock release must include its local catalog. A username match does not prove accounts belong to one person. Exports omit raw usernames and profile URLs.

## Ghidra: inspect an owned binary

Install Ghidra and the required Java runtime separately. The adapter calls its `support/analyzeHeadless` executable, imports one local binary, runs the packaged Java summary script and deletes the temporary project.

```bash
aegis-security run ghidra /absolute/authorized/application.bin --scope scope.json \
  --execute --executable /absolute/ghidra/support/analyzeHeadless
```

The summary contains function count, external symbol count and executable memory bytes. The wrapper does not execute the binary. Static parsing processes untrusted content; use a restricted OS account/container as needed. A real Ghidra/JDK installation requires its own smoke test; adapter tests verify command and summary contracts.

## mitmproxy: audit an owned application's egress

Import a private HAR with exact authorized hostnames in `scope.hosts`:

```bash
aegis-security import mitmproxy /absolute/authorized/reports/app.har --scope scope.json
```

Exports discard headers, cookies, query strings, bodies and full URLs. An optional addon prints only authorized host/status/TLS observations during an operator-started test session:

```bash
mitmdump -s tools/mitmproxy/ethos_aegis_addon.py \
  --set aegis_hosts=app.example.test --quiet > /absolute/authorized/reports/flows.jsonl
aegis-security import mitmproxy /absolute/authorized/reports/flows.jsonl --scope scope.json
```

Follow mitmproxy's own device proxy and certificate instructions. The wrapper does not start a proxy or change device trust settings. Native .mitm dumps are not parsed by this stdlib package; use a trusted local exporter or the addon.

## ESP32 Marauder: import a lab inventory

Review an owned device's local results, then create operator-selected summary records. This is an **Ethos Aegis interchange schema**, not a native Marauder export claim:

```json
{"schema":"ethos-aegis.marauder.v1","device_id":"owned-lab-board","protocol":"wifi","observations":3}
```

Add that label to `scope.devices` and import JSONL. Exported evidence hashes the label and retains only protocol and observation count. MACs, SSIDs, captures and firmware logs are omitted. No radio commands or firmware flashing are implemented.

## Evidence and review

Reports carry schema version, source SHA-256, record count, import/execution mode and stable IDs for identical normalized observations. SHA-256 establishes byte provenance, not producer authenticity or scan completeness. A changed export changes its source hash and may change IDs.

```python
from ethos_aegis.security_toolkit import SecurityToolkit, ToolId
report = SecurityToolkit(trusted_scope).import_report(ToolId.TRUFFLEHOG, evidence_path)
candidate = report.findings[0].to_candidate()
# ConfidenceLevel.HYPOTHESIS; use task verification and patch assessment separately.
```

Input is limited to 8 MiB and 10,000 records. Commands use fixed argv, no shell, a 60-second default time budget (maximum 300), bounded stdout, discarded stderr, a small environment allowlist and temporary directories. POSIX process groups are terminated on completion/failure; Windows child containment needs an external job/container boundary. These checks do not establish OS isolation or enforce network destinations.

Empty findings do not establish a safe target. Normalization does not establish tool accuracy, ownership, complete coverage or authenticated evidence.

## Primary sources

- [Sherlock flags and CSV contract](https://github.com/sherlock-project/sherlock/blob/master/sherlock_project/sherlock.py)
- [Ghidra headless arguments](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/RuntimeScripts/support/analyzeHeadlessREADME.md)
- [Ghidra script API](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/Features/Base/src/main/java/ghidra/app/script/GhidraScript.java)
- [mitmproxy addon examples](https://github.com/mitmproxy/mitmproxy/tree/main/examples/addons)
- [TruffleHog](https://github.com/trufflesecurity/trufflehog)
- [ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder)

See [recordings](../demos/README.md), [archive integration](../veriflow_immune_system.md) and [third-party notices](../../THIRD_PARTY_NOTICES.md).
