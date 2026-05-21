# How `docs.yml` keeps the README current

The `.github/workflows/docs.yml` workflow is the engine that makes a stale
README a CI failure rather than a documentation debt item. This guide
explains exactly what it does, where the safeguards live, and how the
verification was performed.

## The contract

| Trigger | What happens | Effect on the repo |
|---|---|---|
| **Push to `main`** | Sync README → run examples → re-sync with `LDT_FORCE_STAMP=1` → diff → commit back the diff if any | README's `last-verified` timestamp and any drifted output snapshots are refreshed in a follow-up commit by `github-actions[bot]`. |
| **Pull request** | Sync README → run examples → re-sync (no stamp bump) → diff | If the diff is non-empty, the PR job fails with an error pointing to `npm run docs`. The timestamp deliberately is **not** bumped on PRs — only content drift fails them. |
| **Push to a feature branch** | Sync → run → re-sync (no stamp bump) | No commit-back, no failure. Diagnostic only. |
| **`workflow_dispatch`** | Sync → run → re-sync (no stamp bump) | Same as feature-branch push. |

## The infinite-loop safeguard

The commit-back step on `main` pushes back to `main`. Without protection
this would re-trigger `docs.yml` on the bot's own commit, which would
re-bump the timestamp, push again, retrigger again, forever.

There are **two independent safeguards** keeping that from happening, and
either alone is sufficient — both together are defense-in-depth.

### Safeguard 1 — GitHub platform behavior

When the commit-back uses `secrets.GITHUB_TOKEN` (as it does today), the
resulting push does not create new workflow runs. This is a documented
GitHub platform behavior, not something configured in this repo:

> When you use the repository's `GITHUB_TOKEN` to perform tasks, events
> triggered by the `GITHUB_TOKEN` will not create a new workflow run.
> This prevents you from accidentally creating recursive workflow runs.
> — [GitHub Actions documentation](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication#using-the-github_token-in-a-workflow)

This safeguard would only ever fail if the commit-back step were switched
to push using a PAT, which is unusual and should be considered a red flag
in code review.

### Safeguard 2 — Commit-message prefix guard

The workflow's `regenerate` job has a top-level `if:` guard:

```yaml
if: "${{ !startsWith(github.event.head_commit.message, 'docs refresh README snippets') }}"
```

If for any reason a push reaches this workflow whose head commit's first
line is exactly the sentinel `docs refresh README snippets …`, the
regenerate job is skipped. The commit-back step itself uses that exact
sentinel as the first line of its commit message:

```yaml
git commit -m "docs refresh README snippets + output snapshots"
```

`startsWith` is used instead of `contains` so that an unrelated human
commit which merely *quotes* the sentinel in its body (e.g. when a PR
description gets copied into the merge commit) still triggers the
workflow normally.

## Verification

The safeguards were verified live against the last five real bot commits
on `main`:

| Bot commit (short SHA) | Trigger PR | Re-triggered `docs.yml`? |
|---|---|---|
| `7c93467` | #27 | No |
| `3b0ed5d` | #26 | No |
| `48e5426` | #22 | No |
| `500c09b` | earlier | No |
| `ab6bba9` | earlier | No |

All five were inspected with `gh run list --workflow=docs.yml
--commit=<sha>`, which returned an empty list in every case — confirming
that no `docs.yml` run was associated with the bot's push. This shows
safeguard 1 is actively working in production; safeguard 2 was not
needed to fire.

The PR-merge runs on the merge commits themselves succeeded as expected
and produced the bot commits in the table above.

## When you might break this

| Change | Risk | Mitigation |
|---|---|---|
| Rewriting the `Commit back to main` step's commit message | Breaks safeguard 2. | Keep the literal phrase `docs refresh README snippets` as the **first line** of the commit message. The guard uses `startsWith`. |
| Switching the commit-back from `secrets.GITHUB_TOKEN` to a PAT | Bypasses safeguard 1; safeguard 2 becomes load-bearing. | Make sure safeguard 2's `if:` guard is still keyed on the same commit-message prefix as the new commit step. |
| Removing the `LDT_FORCE_STAMP=1` re-sync on main | Eliminates the timestamp drift, so the commit-back may rarely fire — but the workflow still does its real job of catching content drift. | Acceptable trade-off if you decide a moving timestamp isn't worth the bot commits in history. |
| Adding a different commit-back step (e.g. for `examples.yml`) | Could re-trigger `docs.yml` if its commit message doesn't match the guard. | Either keep `examples.yml` from pushing to `main` at all, or extend the guard's `startsWith` to accept the new prefix too. |
