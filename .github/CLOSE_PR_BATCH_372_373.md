# Bulk PR Closure Manifest

This document tracks the closure of conflicting/deprecated PRs as part of the main branch cleanup (2026-10-01).

## Rationale

PRs #372, #373, #328, #335, #310, #311, #312, #313, #354 target feature branches or contain reverts that are no longer actionable. They conflict with the current main HEAD and cannot be rebased meaningfully.

**Action:** Close all with standardized explanatory comment.

## PR Disposition

| PR | Title | Reason | Status |
|---|---|---|---|
| #372 | Revert "Run" | Wrong base branch (palette-repl-ux-enhancements) | To Close |
| #373 | Revert "Run (#245)" | Duplicate revert, conflicting with main | To Close |
| #328 | Revert 282 dependabot/npm and yarn/tsx 4.23.13 | Feature branch base; outdated | To Close |
| #335 | Revert 282... (#331) | Duplicate of #328 | To Close |
| #310 | Revert 247 main | Wrong base; superseded | To Close |
| #311 | Non/to main (#294) | Unclear intent; wrong base | To Close |
| #312 | ci: add macOS Private Shield compatibility gate | Feature branch base; see #316 | To Close |
| #313 | Non/to main (#294) | Duplicate of #311 | To Close |
| #354 | docs(private-shield): specify broker MCP and cross-platform boundaries | Duplicate of #352 | To Close |

## Closure Comment Template

```
**Bulk PR Cleanup (2026-10-01)**

This PR has been closed as part of a systematic conflict resolution on the main branch. 

**Reason:** This PR targets a feature branch or contains changes that conflict with the current main HEAD. The branch cannot be rebased meaningfully without manual intervention.

**Next Steps:**
- If this work is still needed, please create a fresh PR against current `main` (commit 473660267fa5a4d26e66a3d5fb1e01a84c48fd7b).
- Core security fixes (#293, #298) and platform broker features are being re-applied as clean PRs.
- CI gates and documentation will be consolidated into new PRs after base merge.

**Reference:** Security hardening PRs #293 and #298 contain related guards and documentation. See those PRs for the full security audit.
```

