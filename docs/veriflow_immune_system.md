# VeriFlow archive integration

The uploaded Agentic Immune VeriFlow archive contributes Boolean expressions, public imports, SDK references and change-triggered intake. The newer repository CKAN ingestion, capability probes, host-scoped persistence and data fingerprint implementations remain the active engine.

Boolean rules include double negation, De Morgan, identity, domination, idempotence and selected absorption. Truth-table tests verify these rewrites preserve meaning. This is a small simplifier, not a general theorem prover or authorization engine.

```python
from ethos_aegis.veriflow import And, Not, Symbol, simplify
rule = Not(Not(And(Symbol("owned"), Symbol("allowed"))))
print(simplify(rule))  # (owned ∧ allowed)
```

VeriflowReasoner ranks supported formula candidates using fit, semantic alignment, coverage, stability and complexity. A fitted formula is not a scientific law or causal claim.

```bash
python -m ethos_aegis.security_toolkit demo --scenario veriflow
```

AutonomicSentinel emits hash-linked observations for changed Python files. AST inspection identifies direct eval/exec calls, excludes links/hidden directories and enforces budgets. It never rewrites files. Reachability and behavior need independent verification. The archive's broad string replacements were mapped to the existing PatchValidationScaffold instead of enabled as automatic repairs.

```python
from ethos_aegis.agent.scaffolds import AutonomicSentinel
for activation in AutonomicSentinel("/absolute/owned/repository").poll_once():
    print(activation.relative_path, activation.sha256_after)
```

The [integration register](provenance/archive-integration.json) records each extracted source file and its disposition.
