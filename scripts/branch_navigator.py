#!/usr/bin/env python3
"""Read-only, fail-closed GitHub branch navigation snapshot (stdlib only)."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class EvidenceError(RuntimeError):
    """Required GitHub evidence is incomplete or unavailable."""


class GitHub:
    def __init__(self, repo: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise EvidenceError("Invalid GITHUB_REPOSITORY")
        if not token:
            raise EvidenceError("GITHUB_TOKEN is missing")
        self.repo = repo
        self.root = f"https://api.github.com/repos/{repo}"
        self.token = token

    def get(self, path: str):
        url = path if path.startswith("https://") else self.root + path
        if urlparse(url).hostname != "api.github.com":
            raise EvidenceError("Refusing untrusted pagination URL")
        req = Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "safe-branch-navigator/1.0",
        })
        try:
            with urlopen(req, timeout=25) as response:
                return json.load(response), response.headers.get("Link", "")
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise EvidenceError(f"GitHub API evidence unavailable: {url}: {exc}") from exc

    def one(self, path: str):
        return self.get(path)[0]

    def pages(self, path: str, field: str | None = None):
        url = path
        results = []
        count = 0
        while url:
            count += 1
            if count > 100:
                raise EvidenceError("Pagination exceeds safe 100-page cap")
            value, link = self.get(url)
            page = value if field is None else value.get(field)
            if not isinstance(page, list):
                raise EvidenceError(f"Malformed GitHub page: {path}")
            results.extend(page)
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = match.group(1) if match else None
        return results

    def compare(self, base: str, head: str):
        return self.one(f"/compare/{quote(base, safe='')}...{quote(head, safe='')}")

    def evidence(self, sha: str, expected: list[str]):
        sha = quote(sha, safe="")
        checks = self.pages(f"/commits/{sha}/check-runs?filter=latest&per_page=100", "check_runs")
        statuses = self.one(f"/commits/{sha}/status").get("statuses")
        runs = self.pages(f"/actions/runs?head_sha={sha}&per_page=100", "workflow_runs")
        if not isinstance(statuses, list):
            raise EvidenceError("Commit statuses payload missing")
        latest = {}
        for run in runs:
            if run.get("name") in {"Branch navigator", "Branch navigator tests"}:
                continue
            key = run.get("workflow_id")
            if key is None:
                raise EvidenceError("Actions run without workflow_id")
            stamp = (run.get("run_number", 0), run.get("run_attempt", 0), run.get("created_at", ""))
            if key not in latest or stamp > latest[key][0]:
                latest[key] = (stamp, run)
        observed_runs = [v[1] for v in latest.values()]
        checks_by_name = {}
        for check in checks:
            key = ((check.get("app") or {}).get("id"), check.get("name"))
            stamp = (check.get("completed_at") or check.get("started_at") or "", check.get("id", 0))
            if key not in checks_by_name or stamp > checks_by_name[key][0]:
                checks_by_name[key] = (stamp, check)
        latest_status = {}
        for status in statuses:
            key = status.get("context")
            if key not in latest_status:
                latest_status[key] = status
        bad = []
        for c in checks_by_name.values():
            check = c[1]
            if check.get("status") != "completed" or check.get("conclusion") != "success":
                bad.append(f"check:{check.get('name')}={check.get('conclusion') or check.get('status')}")
        for status in latest_status.values():
            if status.get("state") != "success":
                bad.append(f"status:{status.get('context')}={status.get('state')}")
        for run in observed_runs:
            if run.get("status") != "completed" or run.get("conclusion") != "success":
                bad.append(f"workflow:{run.get('name')}={run.get('conclusion') or run.get('status')}")
        present = {run.get("name") for run in observed_runs}
        bad.extend(f"missing-workflow:{name}" for name in expected if name not in present)
        if not (checks_by_name or latest_status or observed_runs):
            bad.append("no-CI-evidence")
        return {"green": not bad, "blockers": sorted(set(bad)),
                "check_count": len(checks_by_name), "status_count": len(latest_status),
                "workflow_count": len(observed_runs)}


def depth(branch: str, dependencies: dict[str, str], visiting=None) -> int:
    visiting = set() if visiting is None else visiting
    if branch in visiting:
        raise EvidenceError(f"Cyclic PR base dependency at {branch}")
    parent = dependencies.get(branch)
    if parent not in dependencies:
        return 1
    return 1 + depth(parent, dependencies, visiting | {branch})


def plan(branches: list[dict], prs: list[dict], default: str, selected_base: str,
         compares: dict, ancestry: dict, ci: dict, expected: list[str]) -> dict:
    names = {b["name"] for b in branches}
    if default not in names or selected_base not in names:
        raise EvidenceError("Default or selected base branch missing")
    if len(names) != len(branches):
        raise EvidenceError("Duplicate branch entries")
    for b in branches:
        if not b.get("commit", {}).get("sha") or not isinstance(b.get("protected"), bool):
            raise EvidenceError("Branch SHA or protection status missing")
    default_problem = not ci[default]["green"]
    open_heads = {}
    used_bases = set()
    for pr in prs:
        head = (pr.get("head") or {}).get("ref")
        base = (pr.get("base") or {}).get("ref")
        same_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name") == ((pr.get("base") or {}).get("repo") or {}).get("full_name")
        if base in names:
            used_bases.add(base)
        if same_repo and head in names:
            open_heads.setdefault(head, []).append(pr)
    deps = {}
    for b in branches:
        name = b["name"]
        if name != default:
            found = open_heads.get(name, [])
            deps[name] = found[0]["base"]["ref"] if len(found) == 1 else (default if name == selected_base else selected_base)
    problems = set()
    for name in deps:
        try:
            depth(name, deps)
        except EvidenceError:
            problems.add(name)
    rows = []
    for b in branches:
        name = b["name"]
        sha = b["commit"]["sha"]
        if name == default:
            continue
        assigned_prs = open_heads.get(name, [])
        base = deps[name]
        cmp = compares.get(name, {})
        anc = ancestry.get(name, False)
        is_protected = b["protected"]
        eligible_delete = (not is_protected and name != selected_base and anc
                           and not assigned_prs and name not in used_bases
                           and ci[default]["green"])
        if eligible_delete:
            action, reason = "DELETE", "Exact head commit is contained in green default branch; no open PR uses this ref"
        elif is_protected or name == selected_base:
            action, reason = "RETAIN", "Protected or selected base branch"
        elif name in problems or len(assigned_prs) > 1:
            action, reason = "REVIEW_DEPENDENCY", "Cyclic or ambiguous PR targeting"
        elif len(assigned_prs) == 0:
            action, reason = "COMPARE", "No open PR; review intended base and changes before opening one"
        elif not cmp:
            action, reason = "REVIEW_COMPARISON", "Comparison evidence unavailable"
        elif cmp["behind_by"] > 0:
            action, reason = "SYNC", "Head is behind its PR base; update branch and rerun CI"
        elif assigned_prs[0].get("draft"):
            action, reason = "REVIEW_DRAFT", "Mark PR ready only after review"
        elif not ci[name]["green"]:
            action, reason = "FIX_CI", "Head/PR workflow evidence not green"
        elif not ci.get(base, {"green": False})["green"]:
            action, reason = "FIX_BASE_CI", "Destination workflow evidence not green"
        elif default_problem:
            action, reason = "FIX_DEFAULT_CI", "Default branch has failing or missing CI"
        else:
            action, reason = "REVIEW_MERGE", "Evidence green; inspect PR merge box, rulesets and reviews before human merge"
        pr_url = assigned_prs[0].get("html_url") if len(assigned_prs) == 1 else None
        safe_head = quote(name, safe="")
        safe_base = quote(base, safe="")
        rows.append({"head": name, "sha": sha, "base": base,
                     "pr": pr_url, "compare_url": f"https://github.com/{{repo}}/compare/{safe_base}...{safe_head}",
                     "branch_url": f"https://github.com/{{repo}}/tree/{safe_head}",
                     "action": action, "reason": reason, "depth": depth(name, deps) if name not in problems else 999,
                     "ahead": cmp.get("ahead_by"), "behind": cmp.get("behind_by"),
                     "protected": is_protected, "ancestor_of_default": anc,
                     "ci": ci[name]})
    rank = {"REVIEW_DEPENDENCY": 0, "FIX_BASE_CI": 1, "FIX_DEFAULT_CI": 1,
            "SYNC": 2, "FIX_CI": 3, "REVIEW_MERGE": 4, "REVIEW_DRAFT": 5,
            "REVIEW_COMPARISON": 6, "COMPARE": 6, "DELETE": 7, "RETAIN": 9}
    rows.sort(key=lambda r: (r["depth"], rank[r["action"]], r["head"]))
    next_row = next((r for r in rows if r["action"] != "RETAIN"), None)
    return {"default": default, "default_ci": ci[default], "selected_base": selected_base,
            "expected_workflows": expected, "branches": rows, "next": next_row,
            "complete": next_row is None and ci[default]["green"]}


def render(snapshot: dict, repo: str) -> str:
    link = lambda row: row["pr"] or row["compare_url"].replace("{repo}", repo)
    lines = ["# Branch navigator", "", f"Repository: `{repo}` · Default: `{snapshot['default']}`",
             f"Snapshot (UTC): `{snapshot['created_at']}`", ""]
    current = snapshot["next"]
    if current:
        lines += ["> [!IMPORTANT]", f"> **NEXT — {current['action']}**: [{current['head']}]({link(current)}) → `{current['base']}`",
                  f"> {current['reason']}", f"> Verified snapshot head: `{current['sha']}` (recheck SHA before clicking)", ""]
    else:
        lines += ["> [!IMPORTANT]", "> **NO ELIGIBLE TOPIC ACTION** — review retained branches and default-branch CI.", ""]
    lines += [f"Default CI: **{'GREEN' if snapshot['default_ci']['green'] else 'HOLD'}**",
              f"Blockers: `{', '.join(snapshot['default_ci']['blockers']) or 'none'}`", "",
              "| Head → base | SHA | Ahead / behind | CI | Action |", "|---|---|---|---|---|"]
    for r in snapshot["branches"]:
        name = r["head"].replace("|", "\\|")
        lines.append(f"| [{name}]({link(r)}) → `{r['base']}` | `{r['sha'][:12]}` | {r['ahead']} / {r['behind']} | {'GREEN' if r['ci']['green'] else 'HOLD'} | **{r['action']}** |")
    lines += ["", "**Important:** Advisory only. Inspect branch compare, current SHA, PR merge box, required reviews, rulesets and all applicable Actions before any action.",
              "A green report does not authorize a merge/deletion, resolve CI failures, or prove a ruleset's requirements are satisfied.",
              "Squash/rebase-equivalent trees do not establish safe deletion; exact commit ancestry is required.", ""]
    return "\n".join(lines)


def snapshot(api: GitHub, selected_base: str, expected: list[str]):
    info = api.one("")
    default = info.get("default_branch")
    if not default:
        raise EvidenceError("Cannot read default branch")
    branches = api.pages("/branches?per_page=100")
    names = {b["name"] for b in branches}
    selected_base = selected_base or default
    if selected_base not in names:
        raise EvidenceError(f"Selected base does not exist: {selected_base}")
    prs = api.pages("/pulls?state=open&per_page=100")
    prs_by_head = {}
    for pr in prs:
        if ((pr.get("head") or {}).get("repo") or {}).get("full_name") == api.repo:
            prs_by_head.setdefault(pr["head"]["ref"], []).append(pr)
    ci = {}
    for b in branches:
        name = b["name"]
        expected_on_branch = expected if (name == default or name in prs_by_head) else []
        ci[name] = api.evidence(b["commit"]["sha"], expected_on_branch)
    compares = {}
    ancestry = {}
    default_sha = next(b["commit"]["sha"] for b in branches if b["name"] == default)
    for b in branches:
        name = b["name"]
        if name == default:
            continue
        prs_for_name = prs_by_head.get(name, [])
        base = prs_for_name[0]["base"]["ref"] if len(prs_for_name) == 1 else selected_base
        if base not in names:
            raise EvidenceError(f"PR base {base} for {name} not found in branch inventory")
        compare = api.compare(base, name)
        if not isinstance(compare.get("ahead_by"), int) or not isinstance(compare.get("behind_by"), int):
            raise EvidenceError(f"Invalid comparison for {name}")
        compares[name] = {"ahead_by": compare["ahead_by"], "behind_by": compare["behind_by"]}
        contained = api.compare(b["commit"]["sha"], default_sha)
        ancestry[name] = contained.get("behind_by") == 0 and isinstance(contained.get("ahead_by"), int)
    result = plan(branches, prs, default, selected_base, compares, ancestry, ci, expected)
    result["repo"] = api.repo
    result["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="")
    parser.add_argument("--output", default="branch-navigation-report")
    args = parser.parse_args(argv)
    try:
        repo = os.environ["GITHUB_REPOSITORY"]
        required = [x.strip() for x in os.getenv("REQUIRED_WORKFLOWS", "").splitlines() if x.strip()]
        result = snapshot(GitHub(repo, os.getenv("GITHUB_TOKEN", "")), args.base, required)
        report = render(result, repo)
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "snapshot.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        (out / "summary.md").write_text(report, encoding="utf-8")
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(report)
        print(report)
        return 0
    except (EvidenceError, KeyError, TypeError) as exc:
        print(f"::error::Branch navigator HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
