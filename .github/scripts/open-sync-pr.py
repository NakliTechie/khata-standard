#!/usr/bin/env python3
"""Commit a sync's changed datasets to a branch and open (or update) its pull request.

    python .github/scripts/open-sync-pr.py <sync-report.json> <primary|fallback>

One branch per run day, so a re-run the same day updates the open PR instead of opening another.
The PR body lists every changed dataset, its provider, row counts and upstream commits, and flags a
fallback run so the reviewer knows the second source was used.
"""
import json
import subprocess
import sys

report_path, providers = sys.argv[1], sys.argv[2]
report = json.load(open(report_path))
day = report["runDate"]
branch = f"sync/upstream-{day}"


def sh(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True).stdout.strip()


changed = {k: v for k, v in report["datasets"].items() if v.get("changed")}
if not changed:
    print("nothing changed")
    sys.exit(0)

sh("git", "config", "user.name", "khata-standard-bot")
sh("git", "config", "user.email", "bot@naklitechie.com")
sh("git", "switch", "-C", branch)
sh("git", "add", "data", "provenance")
if not sh("git", "status", "--porcelain", "--", "data", "provenance"):
    print("no file changes to commit")
    sys.exit(0)
sh("git", "commit", "-m", f"data: upstream sync {day} ({providers}): " + ", ".join(sorted(changed)))
sh("git", "push", "--force-with-lease", "origin", branch)

lines = [f"Automated sync from upstream tax data ({providers} providers), {day}.", ""]
if providers == "fallback":
    lines += ["> **Fallback run.** The primary sources failed; these rows come from the second source. Check them against the primary when it recovers.", ""]
lines += ["| Dataset | Provider | Rows | Overrides | File |", "|---|---|---|---|---|"]
for name, e in sorted(changed.items()):
    lines.append(f"| {name} | {e['provider']} | {e['rows']} | {e['overrides']} | `{e.get('file', '')}` |")
lines += ["", "Upstream files:"]
for name, e in sorted(changed.items()):
    for u in e.get("upstream", []):
        if u.get("note"):
            lines.append(f"- {name}: {u['note']}")
        else:
            lines.append(f"- {name}: {u['repo']}@{u['ref']} `{u['path']}` commit `{(u.get('commit') or 'unknown')[:12]}` ({u['license']})")
lines += ["", "Review: compare the changed rows with the official notification before merging. Rows in "
          "`data/overrides/` win over upstream; correct a wrong upstream value there, with its citation. "
          "Merging publishes the file and `publish.yml` updates `data/index.json`, which Bahi reads."]
body = "\n".join(lines)

existing = sh("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number", "--jq", ".[0].number", check=False)
if existing:
    sh("gh", "pr", "edit", existing, "--body", body)
    print(f"updated PR #{existing}")
else:
    url = sh("gh", "pr", "create", "--base", "main", "--head", branch,
             "--title", f"Upstream tax-data sync {day}" + (" (fallback)" if providers == "fallback" else ""), "--body", body)
    print(url)
