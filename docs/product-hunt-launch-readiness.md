# Ethos Aegis — Product Hunt launch readiness
**State:** Evidence-bounded working checklist; no licensing grant, paid entitlement, warranty, or certification is created by this document.
**Reviewed:** October 8, 2026. Verify all dynamic facts again immediately before launch.

## Distinct package and source scopes

| Component | Declared version | Requirements | License/status |
| --- | --- | --- | --- |
| Repository root `pyproject.toml` | 0.1.0 | Python >=3.12; seven direct dependencies | No license field in the project manifest |
| `python/pyproject.toml` | 1.0.0 | Python >=3.10; no required third-party dependencies declared | Metadata states MIT; root license differs |
| Root `package.json` | 0.1.1, `living-docs-template` | Node >=22.12 | Apache-2.0 metadata; **`private: true`**, not a publishable npm package |
| GitHub Release tag | v1.0.0 (June 11, 2026) | Release tag, not a package-index verification | At audit time: zero attached release assets |
| SDK / imported archive portions | Component-specific | Consult local manifests | Preserve their individual notices; see `THIRD_PARTY_NOTICES.md` |

Do not collapse these independent manifests into one version, Python compatibility, dependency, or license claim. Do not describe the product as production-certified or a fully autonomous protection service based solely on demos or release tags.

## Licensing decision gate — BLOCKED

1. Root `LICENSE` contains **CC0 1.0 Universal**. Its grant is intended to permit commercial reuse, subject to other applicable rights and local law. Do not describe it as MIT or imply a future edit can retroactively revoke valid CC0 permissions.
2. `LICENSE_COMMERCIAL.md` describes **free non-commercial use** and **paid commercial licensing**. It also lists Indie **$99/year**, Startup **$499/year**, Business **$1,499/year**, and Enterprise **contact for pricing**. These are publicly stated proposed terms, **not proof that the terms govern all previously released CC0 material**, that payment is required for CC0 works, or that a working subscription/checkout exists.
3. The Python subtree advertises MIT and the Node scaffold advertises Apache-2.0. Component provenance, historical grants, ownership, third-party rights, and package-specific distribution must be reviewed before deciding what each notice covers.
4. Preserve original license and attribution notices, including imported SDK MIT files and third-party licenses. Any prospective paid commercial product must identify **distinct qualifying deliverables/services** and rights that have not already been granted, such as separate proprietary functionality, a hosted service, contracts, or support (if actually offered).
5. Obtain an explicit maintainer-approved scope decision and qualified legal review before modifying `LICENSE`, `LICENSE_COMMERCIAL.md`, package `license` metadata, or describing a universal mandatory paid license.

## Product Hunt pricing — pending license and offer verification

| Product Hunt category | Appropriate only if actually true |
| --- | --- |
| **Free** | The Product Hunt offering is free to use, with no payment required for what is launched. |
| **Paid** | Access to the launched offering requires payment, with no free plan. |
| **Paid (with a free trial or plan)** | The launch contains a real paid offering plus an actually available free plan or trial. |

**No final category selected.** Public viewing of GitHub/Pages and unverified commercial tiers are not sufficient to establish a paid plan. If a paid hosted or supported tier and a real free tier are later launched, the third category may fit; if only the free source/demo is offered, choose Free. Never relabel CC0 code as paid-only.

**Promo code:** no code, offer, or expiration verified; leave blank. **Funding information:** select Bootstrapped, Y Combinator, or Venture backed only after the maintainer verifies the corresponding funding history; do not infer it from repository ownership.

## Availability — public source vs deployed media

- GitHub repository: `https://github.com/DeontewattsV1/Ethos-Aegis-`
- Public website: `https://deontewattsv1.github.io/Ethos-Aegis-/` — accessible at audit.
- 4D interactive board: `https://deontewattsv1.github.io/Ethos-Aegis-/board.html` — accessible at audit.
- `/docs/demos/toolkit.mp4`, `/docs/demos/immune.mp4`, and `/docs/demos/veriflow.mp4` under the Pages origin: all **HTTP 404** at audit.
- The repository README links to videos and GIF previews, but this does not prove those videos were copied into the currently published Pages artifact, nor that playback works on the published website.
- Check the actual Pages source (branch/folder or Actions artifact), deployment status, media MIME types, direct URLs, and browser playback. Preserve authorization boundaries and synthetic-demo labeling.

## Launch acceptance — no-go until verified

- [ ] License scope, older CC0 grants, MIT SDK notices, Python MIT metadata and Node Apache-2.0 metadata reconciled without removing existing rights.
- [ ] Exact public/free and commercial service/product boundaries, deliverables, support, checkout, and prices confirmed.
- [ ] Product Hunt pricing and funding information chosen from real offer and founder-confirmed records.
- [ ] Package build/install tested for each advertised target; no conflict between package identity, versions, dependencies and supported Python versions.
- [ ] Required tests, security gates, provenance and authorization reviews pass on the exact release commit; no skipped or downgraded gates.
- [ ] Security findings, release assets, and source-to-release tags/SHAs reviewed.
- [ ] Public site home page and board agree with current launch content; all three videos demonstrably return success and play.
- [ ] Product Hunt description makes no unsupported production-certified, zero-dependency, or autonomous live scanning claims.

**Release recommendation:** withhold Product Hunt launch and package-registry publication until legal/offer scope and live-media blockers are resolved.
