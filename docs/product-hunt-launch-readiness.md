# Ethos Aegis — Product Hunt, licensing and packaging readiness

**Status:** Prospective business-model direction approved by the maintainer; release gate remains **NO-GO** pending verified security, package, legal-provenance and website conditions.

**Audit date:** October 8, 2026. Recheck changing registry and CI facts immediately before publishing.

## Product and distribution boundaries

| Distribution / service | Declared source | Requirements and availability | Applicable status |
| --- | --- | --- | --- |
| **Python immune library** — `ethos-aegis` v1.0.0 | `python/pyproject.toml` | Python >=3.10; no required runtime dependencies declared; local install from `./python` | Subtree metadata declares MIT; `python/LICENSE` includes existing project MIT grant. Provenance still requires review. |
| **Python governance engine** — `ethos-aegis-governance` v0.1.0 | Root `pyproject.toml` | Python >=3.12; seven declared direct dependencies; local install from repository root | Root CC0 grant and metadata; package discovery limited to `ethos_core`, `agents`, `graph`, `simulation` |
| **Node SDK** — `@deontewattsv1/ethos-aegis-sdk` v1.0.0 | `sdk/node/package.json` | Published only by `release` event to `https://npm.pkg.github.com` | SDK MIT notice; release-run publication and package visibility not yet independently verified |
| **Node docs scaffold** — `living-docs-template` v0.1.1 | Root `package.json` | Node >=22.12; `private: true`, not a registry distribution | Separate Apache-2.0 manifest metadata |
| **Container** — `ghcr.io/deontewattsv1/ethos-aegis` | Root Dockerfile | **Release Packages #490** (run `37750343335`, at `a04f2a1`) succeeded; contains Node SDK, **not a Python server or full suite** | GHCR visibility and anonymous pull access **not verified** |
| **GitHub Release** — `v1.0.0` | GitHub Releases | Published June 11, 2026; zero attached release assets at audit | Release tag is not proof of PyPI/n﻿pm installation |

Do not conflate the similarly branded Python wheels, npm SDK, container, root scaffold, or release tag. The Python packages have distinct names and are built/tested separately; neither is published by the GitHub Packages registry picker. **Never publish `ethos-aegis` from the repository root.**

## Approved commercial strategy — preserve open-source rights

1. Preserve existing, valid **CC0 1.0 Universal** grants in the repository root and the existing MIT and other component-specific third-party grants. Neither prospective marketing nor a later policy edit can revoke permissions already granted.
2. The Python subtree includes the previously advertised **MIT** license text; imported and separately licensed modules keep their corresponding notices. The root governance wheel uses existing **CC0** terms. Rights/provenance and upstream compatibility still need review before registry publication.
3. `LICENSE_COMMERCIAL.md` now describes **optional paid services and prospective separately marked proprietary add-ons** rather than a blanket charge for commercial use of free source. No fees are required solely for activities permitted by the applicable open-source grant.
4. Future proprietary modules must be clearly segregated and separately contracted/licensed **before** release. Do not retrospectively relabel already distributed CC0/MIT source.
5. The historical indicative commercial service tiers are Indie **$99/year**, Startup **$499/year**, Business **$1,499/year**, and Enterprise **by written quote**. They are **not verified live subscriptions, hosted services, SLA contracts, or payment entitlements**.

A final counsel/provenance review of license scopes remains a launch gate. This project cannot guarantee rights held by third parties or replace separately signed agreements.

## Product Hunt pricing / availability

**Recommended pricing category for the currently accessible public code and demonstration: `Free`**, assuming it remains free at the time of submission. Do **not** select `Paid` or `Paid (with a free plan)` merely because proposed service rates exist. Switch to `Paid (with a free trial or plan)` only if a separately paid service truly becomes available alongside a usable free product.

**Promo code:** blank; no verified offer, code or expiry. **Funding:** owner must verify Bootstrapped, YC-backed or Venture-backed; no status is inferred.

**Public site:** `https://deontewattsv1.github.io/Ethos-Aegis-/` accessible during audit. The 4D demonstration at `/board.html` was reachable. All three Pages URLs `/docs/demos/toolkit.mp4`, `/docs/demos/immune.mp4`, and `/docs/demos/veriflow.mp4` returned **HTTP 404**. Their presence as repository README links is **not** evidence of deployment or playback.

**GitHub Packages:** choose **Containers** to inspect the GHCR image. Do not select Maven, NuGet or RubyGems without corresponding artifacts. Node SDK npm publishing occurs only on GitHub Release events; `workflow_dispatch` run #490 intentionally skipped npm. The root docs scaffold must stay private. The container has separate visibility from the repository. Publishing to a public package registry or changing package visibility is an explicit, independently verified release decision; it was **not** performed as part of this cleanup.

## Release acceptance criteria

- [ ] Explicit rights/provenance review approves CC0-root, MIT-subtree/SDK, third-party notices and prospectively optional paid-services language without retroactive restriction.
- [ ] Python CI builds isolated, correctly named governance and immune wheels/sdists, verifies wheel contents/licenses/working entry points, and validates full required test/security coverage on the candidate SHA.
- [ ] Each advertised Python version is supported by actual matrix checks; user-facing local install instructions succeed for both distributions.
- [ ] Confirm PyPI account ownership/namespace availability; publish a named version only via a separately approved, verified workflow.
- [ ] Confirm GHCR image manifest/package visibility and inspect entrypoint runtime behavior. A successful push is not proof of a functional web server.
- [ ] Resolve any outstanding P1/P2 security findings and preserve required security, CI, authorization, signed-commit, and review gates.
- [ ] Website homepage and 4D board match release copy; all three MP4 URLs return success with correct media type and are playable.
- [ ] If offered, paid plans have actual deliverables, terms, payment path, and support commitments.
- [ ] Confirm funding and any actual Product Hunt promo details; reject unsupported 'production-certified', 'zero-dependency across all packages' and 'autonomous live protection' claims.

**Publishing disposition: NO-GO until these gates pass.** This document is a configuration/marketing decision record, not proof of title, security assurance, product availability or legal clearance.
