# Branch navigator

**Status:** Advisory-only · **Privacy:** repository metadata and commit SHA snapshot, not source-code archiving.

## Use

Once the workflow files have passed review and have been merged into the repository's **default branch**, open **Actions → Branch navigator → Run workflow**. Open the completed run's **Summary** and select the highlighted **NEXT** link. The same `summary.md` and `snapshot.json` are saved in the `branch-navigation-report` artifact. Scheduled reports run daily at **06:23 UTC**.

The optional `base_branch` input applies only to branches **without** an open PR. Existing PRs determine their own base; the current repository default remains the normal destination. On forks or repositories with different workflows, adjust `REQUIRED_WORKFLOWS` to the actual on-PR/default workflow names, and inspect applicable event-specific checks.

## Safe order

1. Inspect the branch head, destination and **recorded SHA**. The report is a snapshot; always verify the live SHA.
2. Open its PR or comparison. GitHub's `base...head` compares changes since merge base (three-dot); also inspect current snapshot differences (two-dot) when necessary.
3. Resolve PR dependencies **parent first**. For `feature-b → feature-a → main`, integrate `feature-a` into `main` first; then retarget and re-review `feature-b` to `main`.
4. If the head is behind, synchronize base into head, resolve conflicts, rerun CI, and obtain required reviews. A changed SHA invalidates the old snapshot.
5. Only merge from GitHub's live PR merge box after verifying required status checks, reviews, rulesets and permissions. **Do not use admin bypass.** Green advisory checks are insufficient alone.
6. Verify destination commit and Actions, then **run the navigator again**. Delete only when the exact recorded head commit is an ancestor of the green default branch, with no open PR referencing it as head or base and no protection on it.
7. Run again after every merge, retarget, sync or deletion. The process ends when no eligible topic action remains and the default branch's expected checks are green. Retained protected branches are reported, not deleted.

Turn off GitHub's optional **automatically delete head branches** setting if deletion must await post-merge verification. A squash/rebase-merged PR, a closed PR, or an identical file tree does **not** prove exact commit ancestry; those cases require manual reconciliation before deletion.

## Color and highlighting limits

GitHub Actions can highlight `NEXT` links in a run summary but **cannot recolor, highlight, or click items in GitHub's native branch picker**. This tool cannot trigger workflows, repair CI, merge PRs, resolve conflicts, delete branches, or change protection settings. All GitHub operations by this tool are read-only.

## What GREEN means

The tool checks the specific recorded SHA: latest check runs, most recent combined commit-status contexts, and newest completed/incomplete workflow attempts per workflow ID. Only `success` is green; skipped, cancelled, neutral, failed, pending and missing evidence remain HOLD. The report excludes its own workflow and test runs to avoid self-blocking.

The pinned expected-workflow set for Ethos-Aegis is:

- `Ethos Aegis CI`
- `CodeQL Advanced`
- `examples`
- `Security Toolkit`

These names are required on the **default** and any PR head branch. This is a conservative approximation: GitHub PR merge refs can have different CI evidence from branch heads, and `head_sha` filters may not expose a PR's merge-commit jobs. A false HOLD may result, but never treat this as permission to skip checks. The tool also does **not** fully evaluate rulesets, conditional jobs, path/event-specific and required-workflow requirements, CODEOWNERS, merge queues, deployment gates, or independent reviews. The live GitHub PR merge box and actual branch protection remain authoritative. For repositories with a merge queue, use the queue.

API errors, rate limiting, missing/incomplete JSON, malformed required SHA, and unknown branch protection status cause the report to **fail closed**. The job has a 30-minute timeout; a very large repository may require pagination/rate-limit tuning before it can produce a complete snapshot.

## Development

```bash
python3 -m unittest discover -s tests -p test_branch_navigator.py -v
```

No Python dependencies, personal tokens, write permissions or third-party API services are required beyond GitHub's read-only workflow token. The separate `Branch navigator tests` workflow runs the regression suite when navigator code or workflows change.
