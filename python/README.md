<p align="center">
  <img src="../assets/brand/03-wordmark-lockup.svg" alt="Ethos Aegis" width="60%" />
</p>

# `python/` — Ethos Aegis Python Subtree

This directory contains the **Ethos Aegis** Python package — the broader
research codebase that the TypeScript `living-docs-template` scaffold at the
root of this repo demonstrates. It is integrated here as a self-contained
subtree so the two language stacks can evolve side-by-side without their
build tooling colliding.

The TypeScript scaffold and the Python subtree share **nothing at the
language level** — different lockfiles, different CI workflows, different
test runners. The only shared concept is the living-docs philosophy: every
file in this tree is exercised by tests, and the tests run in CI.

## Layout

```
python/
├── ethos_aegis/                 ← Python package (zero runtime deps)
│   ├── agent/                   ← Sentinel AI orchestration + LLM adapters
│   ├── core/                    ← Aegis verdict pipeline
│   ├── security/                ← Vault & integrity primitives
│   ├── veriflow/                ← CKAN-backed dataset verification
│   └── vitality/                ← Health & performance protocol
├── tests/                       ← pytest suite
├── pyproject.toml               ← PEP 621 + ruff + mypy + pytest config
└── requirements.txt             ← Dev/testing dependency pins
```

## Quick start

```bash
cd python
python -m pip install -e '.[dev]'
python -m pytest
```

The exact number of passing or skipped tests depends on the revision and optional integrations. Follow the current Python 3.10/3.11/3.12 CI matrix and do not treat historical test totals as a release guarantee.

## Distribution and installed commands

The canonical immune-system Python distribution is **`ethos-aegis` 1.0.0**,
built from this `python/` directory. It declares Python **>=3.10** and no
mandatory runtime dependencies. Its MIT declaration is accompanied by
[`LICENSE`](LICENSE), without altering any preexisting valid CC0 grant or
third-party component rights.

The **separate** governance Python distribution at the repository root is
**`ethos-aegis-governance` 0.1.0** (Python **>=3.12**, seven required runtime
dependencies). It packages `ethos_core`, `agents`, `graph` and `simulation`;
it is not the same package as `ethos-aegis`.

`pyproject.toml` is the only authoritative metadata source for this distribution.
`setup.py` is a setuptools compatibility shim and must not duplicate versions,
dependency declarations, supported Python versions or console scripts.

The installed CLI supported by this distribution is:

```bash
aegis-security catalog
aegis-security demo --scenario toolkit
```

The Python demo and HTTP server are available as **source-tree scripts**, not as
installed `ethos-aegis` or `aegis-server` commands:

```bash
python scripts/demo.py --quiet
python server.py --help
```

Packaging CI must build the immune and governance wheels separately, audit their
contained modules and license files, and never upload either distribution to
PyPI without a distinct release authorization.

## Known preexisting issues

Two tests in the upstream snapshot are skipped via `--deselect` in
[`pyproject.toml`](./pyproject.toml) and are tracked for follow-up:

| Test | Why skipped | Fix scope |
|---|---|---|
| `tests/test_scaffolds.py::test_verifier_combines_hooks` | `KEYWORD_HOOK` resolves filesystem paths against pytest's `rootdir` instead of the package root; under this layout the fixture's `README.md` is invisible. | Patch the hook to anchor on `Path(__file__).resolve().parents[2]`. |
| `tests/test_suite.py::TestEthosAegisPipeline::test_aegis_verdict_has_all_fields` | Timing assertion `verdict.adjudication_time > 0` is flaky on fast hardware where the pipeline completes inside one monotonic-clock tick (`time.perf_counter` returned `0.0`). | Either widen the assertion to `>= 0` or switch the pipeline to `time.monotonic_ns()`. |

A third file (`tests/test_server.py`) was dropped from this integration
because it hardcoded `cwd="/home/claude/ETHOS_AEGIS"` and could not run in
any CI environment without modification.

## How this integrates with the root living-docs scaffold

| Surface | TypeScript side | Python side |
|---|---|---|
| CI workflow | `.github/workflows/examples.yml` runs `npm test`, executes `examples/*.ts`, and checks snapshot drift | `.github/workflows/python.yml` runs `pytest` |
| Test command | `npm test` (vitest) | `cd python && python -m pytest` |
| Lint command | `npm run lint` (tsc --noEmit) | `cd python && ruff check .` |
| README contract | README region markers refer to `examples/*.ts` files | This README's commands are exercised by `python.yml` on every push |

The TypeScript root and the `python/` subtree are independent: changes to
one do not require changes to the other, and neither imports from the
other at runtime.
