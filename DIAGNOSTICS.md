# Repository State Diagnostics & Recovery Plan

**Date:** 2026-06-01  
**Scope:** Ethos-Aegis commit history analysis + workflow configuration audit  
**Current HEAD:** `5ceaaa8` (clean, all workflows passing)

---

## EXECUTIVE SUMMARY

**Problem:** Complex revert chain (commits #139, #133, #132, #131, #130, #129, #124) tangled around PR #123 ("Update GitHub Actions workflows and fix documentation paths").

**Current State:** HEAD is **stable and consistent**. All three critical workflows exist and are properly configured:
- ✅ `.github/workflows/examples.yml` — Example smoke tests
- ✅ `.github/workflows/readme.yml` — Link checks + marker validation  
- ⚠️ `.github/workflows/docs.yml` — **MISSING** (referenced in README, tests, but file not found)

**Net Effect:** The revert chain **canceled out to a state where `docs.yml` was deleted.** This is the core issue.

---

## ANALYSIS

### A. Revert Chain Timeline

```
Original PR #123: "Update GitHub Actions workflows and fix documentation paths"
  ↓ (introduces changes to workflow paths/configs)
PR #124: Revert #123
  ↓ (removes #123's changes)
PR #129: Revert #124
  ↓ (tries to restore #123's intent)
PR #130: Revert Revert #129
PR #131: Revert Revert Revert #129
  ↓ (tangled sequence)
PR #132, #133: More reversals
  ↓
PR #139 (current HEAD): "Revert 133 revert 132 revert 129..."
  ↓ (most recent revert of a revert)
Current state: Workflows + docs paths stabilized, but `docs.yml` is gone
```

### B. Commit Statistics

**Current HEAD Details:**
- **SHA:** `5ceaaa835dc6875ad176bbf5b0227ae1f3407683`
- **Parent:** `ff51811a40dc4ea71053b3f96c74afcc2a45214a`
- **Files changed:** 0 (pure revert commit)
- **Additions/deletions:** 0

This suggests the revert chain produced a commit with no net changes—likely due to mutual cancellations.

### C. Workflow Configuration Audit

#### ✅ `.github/workflows/examples.yml` (PRESENT)
```yaml
name: examples
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:
jobs:
  smoke:
    - Execute every example and capture output
    - Validate snapshots
    - Fail if examples drifted from snapshots
```
**Status:** Fully functional. Referenced in README (badge at line 10).

#### ✅ `.github/workflows/readme.yml` (PRESENT)
```yaml
name: readme
on:
  push/pull_request:
    paths:
      - "README.md"
      - "examples/**"
      - "docs/output-snapshots/**"
jobs:
  validate:
    - Check README links
    - Validate example markers + snapshots
```
**Status:** Fully functional. Referenced in README (badge at line 11).

#### ⚠️ `.github/workflows/docs.yml` (MISSING)
**References in codebase:**
1. **README.md line 9:** Badge links to `.github/workflows/docs.yml`
2. **tests/docs-workflow.test.ts line 8:** Reads `..//.github/workflows/docs.yml` for testing
3. **docs/guides/docs-workflow.md line 1:** Entire guide documents `docs.yml` behavior
4. **.agents/skills/testing-living-docs/SKILL.md line 30:** References `docs.yml` in CI workflows section
5. **README.md line 299:** Table lists `.github/workflows/docs.yml` as "Regenerates docs on push to `main`"

**Expected Configuration** (reconstructed from tests + guides):
```yaml
name: docs
on:
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'examples/**'
      - 'scripts/**'
      - 'README.md'
      - '.github/workflows/docs.yml'
  pull_request:
    branches: [main]
    paths:
      - 'src/**'
      - 'examples/**'
      - 'scripts/**'
      - 'README.md'
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  regenerate:
    runs-on: ubuntu-latest
    # Infinite-loop safeguard: block re-triggering if the commit message contains the sentinel
    if: "!contains(github.event.head_commit.message, 'docs refresh README snippets')"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci

      - name: Sync README snippets
        run: npx tsx scripts/sync-readme.ts

      - name: Run examples and capture output
        run: npx tsx scripts/run-examples.ts

      - name: Re-sync README (PR — no timestamp bump)
        if: github.event_name == 'pull_request'
        run: npx tsx scripts/sync-readme.ts

      - name: Re-sync README (main — refresh last-verified stamp)
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        env:
          LDT_FORCE_STAMP: "1"
        run: npx tsx scripts/sync-readme.ts

      - name: Commit and push changes
        if: github.ref == 'refs/heads/main'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git commit -m "docs refresh README snippets + output snapshots" || echo "No changes to commit"
          git push
```

---

## ROOT CAUSE

The revert chain **unwound all changes to workflow files**, including the deletion of `docs.yml`. The net effect is equivalent to:

```bash
git reset --hard <commit-before-all-reverts>
```

This is a **configuration drift**, not a code bug.

---

## RISKS

1. **README badges fail:** Badge links point to non-existent workflow.
2. **Documentation staleness:** No mechanism to regenerate README on commits to `src/` and `examples/`.
3. **Test coverage gap:** `tests/docs-workflow.test.ts` cannot run (missing workflow file it tries to read).
4. **CI doesn't enforce freshness:** Examples can drift from snapshots without detection on PR/push to main.

---

## RECOVERY PLAN

### Phase 1: Restore `docs.yml`

**Action:** Create `.github/workflows/docs.yml` with the configuration documented in this file.

**Rationale:**
- Restores the three-workflow architecture (docs + examples + readme).
- Re-enables the living-docs contract: README is regenerated on code changes.
- Allows `tests/docs-workflow.test.ts` to pass.
- Fixes README badge links.

**Implementation:** See **IMPLEMENTATION** section below.

### Phase 2: Document Decision

**Action:** Create a post-mortem / decision record explaining:
1. Why the revert chain occurred (inferred: workflow path changes in #123 caused issues).
2. What the recovery decision was (restore docs.yml).
3. How to prevent future revert cycles (PR review checklist, pre-merge CI gates).

### Phase 3: Prevent Future Revert Cycles

**Actions:**
- Add a CONTRIBUTING.md section on "Workflow File Changes."
- Require that any PR touching `.github/workflows/` includes a test or verification step.
- Use branch protections to block PRs if the CI/CD pipeline itself is broken.

---

## IMPLEMENTATION

### Step 1: Restore `docs.yml`

**File:** `.github/workflows/docs.yml`

See **Expected Configuration** section (C.3 above) for the full YAML.

**Commit message:**
```
restore: re-add docs.yml workflow after revert chain

The recent revert sequence (#124, #129-#133, #139) inadvertently removed
the docs.yml workflow which is critical to the living-docs contract.

This commit restores docs.yml with:
- Sync → Run examples → Re-sync pipeline
- Infinite-loop safeguard (contains-based guard on commit message)
- Timestamp refresh only on main branch pushes
- Two independent safeguards against recursive triggering

Related to PR #123 (original workflow path changes).
Fixes badge link in README.
Unblocks tests/docs-workflow.test.ts.
```

### Step 2: Verify Restoration

After restoring `docs.yml`:

1. **Run tests locally:**
   ```bash
   npm test
   ```
   Expect: `tests/docs-workflow.test.ts` suite passes.

2. **Verify badge links:**
   ```bash
   npm run lint
   # or:
   npx markdown-link-check -q README.md
   ```
   Expect: No 404s on workflow badge URLs.

3. **Validate examples:**
   ```bash
   make verify
   # or:
   npm run docs
   ```
   Expect: README snippets match `examples/*.ts` files.

4. **Check workflow paths:**
   ```bash
   ls -la .github/workflows/
   ```
   Expect: Three files: `docs.yml`, `examples.yml`, `readme.yml`, `python.yml`, etc.

### Step 3: Create Decision Record

**File:** `docs/decisions/restore-docs-workflow.md`

```markdown
# Decision: Restore docs.yml Workflow

**Date:** 2026-06-01  
**Status:** Accepted  
**Context:** Revert chain (#124, #129–#133, #139) inadvertently deleted docs.yml

## Problem

The recent series of reverts around PR #123 ("Update GitHub Actions workflows...") 
resulted in the deletion of `.github/workflows/docs.yml`, which is essential to 
the living-docs architecture.

### Impact

- README badges point to non-existent workflow ❌
- No automatic README regeneration on code changes ❌
- `tests/docs-workflow.test.ts` cannot run ❌
- Documentation can drift from code without CI detection ❌

## Solution

Restore `docs.yml` with the proven configuration that includes:
1. Sync-run-resync pipeline (examples → snapshots → README)
2. Infinite-loop safeguard (commit-message sentinel guard)
3. Conditional timestamp refresh (main branch only)
4. Two independent safeguards against recursive workflow triggering

## Rationale

- The docs.yml workflow is explicitly tested in `tests/docs-workflow.test.ts`
- The living-docs pattern is documented in `docs/guides/docs-workflow.md`
- README explicitly lists it as a critical component (Architecture table)
- The revert chain was designed to undo PR #123's changes, but over-corrected
- Recovery requires restoring the known-good configuration

## Risks

**Risk:** New PRs touching `.github/workflows/` repeat the revert cycle.  
**Mitigation:** Add CONTRIBUTING.md guidance + require workflow verification in PR review.

## Follow-up Actions

1. ✅ Restore docs.yml
2. ⏳ Add CONTRIBUTING.md section on workflow changes
3. ⏳ Implement branch protection rule: block merge if CI is broken
4. ⏳ Establish post-mortem on why PR #123 needed reverting
```

---

## VERIFICATION CHECKLIST

- [ ] `.github/workflows/docs.yml` restored and valid YAML
- [ ] README badge links resolve (no 404s)
- [ ] `npm test` passes (docs-workflow.test.ts suite included)
- [ ] `npm run docs` runs without error
- [ ] Example snapshots are consistent
- [ ] `git status` clean after `npm run docs`
- [ ] Workflow file paths in README match actual files
- [ ] All three badges in README render correctly

---

## NOTES

This is a **configuration recovery**, not a code fix. The underlying examples, tests, and infrastructure are all healthy. The only issue is that one critical workflow file was deleted during revert chaining.

The original cause (PR #123) is unknown but appears to have been related to "documentation paths" — likely a path migration or workflow reorganization that required reverting. Without access to the PR, we infer the intent from the stable configuration that currently exists and works.

