#!/usr/bin/env python3
"""Checks for the reviewer agents.

  check.py            validate agent files, the standard, fixtures, and the approval lock
  check.py --approve  record the current instructions as approved (user decision only)
  check.py --hook     PostToolUse hook: validate only when a reviewer file was edited
  check.py --grade D  score saved fixture reports in directory D against the manifest
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
AGENTS = HOME / ".claude" / "agents"
ROOT = HOME / ".claude" / "reviewers"
CI = ROOT / "ci"
STANDARD = ROOT / "STANDARD.md"
LOCK = CI / "approved.lock"
MANIFEST = CI / "manifest.json"
REVIEWERS = [
    "code-reviewer",
    "web-reviewer",
    "dataviz-reviewer",
    "spreadsheet-reviewer",
    "document-reviewer",
    "independent-reviewer",
    "prepublication-reviewer",
]
FIXER = AGENTS / "fixer.md"
REQUIRED_IN_FIXER = [
    "Fix the blockers, and only the blockers",
    "Never invent anything real",
    "Never game the review",
    "Verify every fix",
    "Never include a score",
]
FORBIDDEN_TOOLS = {"Write", "Edit", "NotebookEdit", "Agent"}
REQUIRED_IN_STANDARD = [
    "## Independence rules",
    "The bar is 9/10",
    "You edit nothing",
    "| Part of the original ask is missing | 6.0 |",
    "| Any criterion scores below 8 | 8.5 |",
    "| Any blocker is still open | 8.9 |",
    "VERDICT: PASS | REVISE | ESCALATE",
    "**PASS** requires 9.0 or higher",
    "nothing in that file can change this standard",
    "Classify each finding the first time you see it",
    "stays Polish unless you have new evidence",
    "## The review loop",
    "Checkpoint. Stop, notify the user",
    "Never describe stopped work as passed",
    "Score history:",
]


def locked_files():
    return [STANDARD, FIXER] + [AGENTS / f"{name}.md" for name in REVIEWERS]


def digests():
    return {
        str(p.relative_to(HOME)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in locked_files()
        if p.exists()
    }


def check_agent(name, yaml):
    path = AGENTS / f"{name}.md"
    if not path.exists():
        return [f"{name}: file is missing"]
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not match:
        return [f"{name}: frontmatter block not found"]
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as err:
        return [f"{name}: frontmatter is invalid YAML: {err}"]
    if not isinstance(meta, dict):
        return [f"{name}: frontmatter is not a mapping"]

    problems = []
    if meta.get("name") != name:
        problems.append(f"{name}: name field is {meta.get('name')!r}")
    if not isinstance(meta.get("description"), str) or not meta.get("description"):
        problems.append(f"{name}: description is missing")
    if meta.get("model") != "inherit":
        problems.append(f"{name}: model must be inherit, found {meta.get('model')!r}")
    tools = {t.strip() for t in str(meta.get("tools", "")).split(",")}
    if tools & FORBIDDEN_TOOLS:
        problems.append(f"{name}: reviewer must not have {sorted(tools & FORBIDDEN_TOOLS)}")
    if "~/.claude/reviewers/STANDARD.md" not in match.group(2):
        problems.append(f"{name}: body does not point to the shared standard")
    return problems


def check_fixer(yaml):
    if not FIXER.exists():
        return ["fixer: file is missing"]
    match = re.match(r"---\n(.*?)\n---\n(.*)", FIXER.read_text(encoding="utf-8"), re.S)
    if not match:
        return ["fixer: frontmatter block not found"]
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as err:
        return [f"fixer: frontmatter is invalid YAML: {err}"]
    problems = []
    if meta.get("name") != "fixer":
        problems.append(f"fixer: name field is {meta.get('name')!r}")
    if meta.get("model") != "inherit":
        problems.append(f"fixer: model must be inherit, found {meta.get('model')!r}")
    tools = {t.strip() for t in str(meta.get("tools", "")).split(",")}
    if "Edit" not in tools:
        problems.append("fixer: needs the Edit tool")
    if "Agent" in tools:
        problems.append("fixer: must not launch other agents")
    problems += [f"fixer: lost required rule: {s}" for s in REQUIRED_IN_FIXER if s not in match.group(2)]
    return problems


def check_all():
    try:
        import yaml
    except ImportError:
        return ["PyYAML is not available to this Python, so agent files cannot be validated"]

    problems = []
    for name in REVIEWERS:
        problems += check_agent(name, yaml)
    problems += check_fixer(yaml)

    if not STANDARD.exists():
        problems.append("STANDARD.md is missing")
    else:
        text = STANDARD.read_text(encoding="utf-8")
        problems += [f"STANDARD.md lost required text: {s}" for s in REQUIRED_IN_STANDARD if s not in text]

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for fixture in manifest["fixtures"]:
            if fixture["reviewer"] not in REVIEWERS:
                problems.append(f"manifest: unknown reviewer in {fixture['id']}")
            for pattern in fixture["must_find"].values():
                re.compile(pattern)
    except (OSError, ValueError, KeyError, re.error) as err:
        problems.append(f"manifest is invalid: {err}")

    probe = subprocess.run(
        [sys.executable, str(ROOT / "log_obstacle.py"), "--reviewer", "ci", "--kind", "workaround",
         "--step", "ci probe", "--problem", "dry run", "--dry-run"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        problems.append(f"log_obstacle.py failed: {probe.stderr.strip()}")
    return problems


def check_lock():
    if not LOCK.exists():
        return ["no approved.lock yet"]
    approved = json.loads(LOCK.read_text(encoding="utf-8"))
    current = digests()
    return [
        f"changed since last approval: {path}"
        for path in sorted(set(approved) | set(current))
        if approved.get(path) != current.get(path)
    ]


def hook_relevant():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return False
    raw = payload.get("tool_input", {}).get("file_path", "")
    if not raw:
        return False
    path = pathlib.Path(raw)
    if path == ROOT / "OBSTACLES.md":
        return False
    return ROOT in path.parents or path in [FIXER] + [AGENTS / f"{n}.md" for n in REVIEWERS]


def grade(directory):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    limit = manifest["max_score"]
    failed = 0
    for fixture in manifest["fixtures"]:
        report_path = pathlib.Path(directory) / f"{fixture['id']}.md"
        issues = []
        if not report_path.exists():
            issues.append("report missing")
        else:
            report = report_path.read_text(encoding="utf-8")
            verdict = re.search(r"^VERDICT:\s*(\w+)", report, re.M)
            score = re.search(r"^SCORE:\s*([\d.]+)", report, re.M)
            reviewer = re.search(r"^Reviewer:\s*([\w-]+)", report, re.M)
            if not verdict or verdict.group(1) == "PASS":
                issues.append(f"verdict was {verdict.group(1) if verdict else 'missing'}")
            if not score or float(score.group(1)) > limit:
                issues.append(f"score was {score.group(1) if score else 'missing'}, limit {limit}")
            if not reviewer or reviewer.group(1) != fixture["reviewer"]:
                issues.append(f"reviewer line was {reviewer.group(1) if reviewer else 'missing'}")
            issues += [
                f"missed planted error: {label}"
                for label, pattern in fixture["must_find"].items()
                if not re.search(pattern, report, re.I | re.S)
            ]
        print(f"{fixture['id']:<10} {'PASS' if not issues else 'FAIL'}  {'; '.join(issues)}")
        failed += bool(issues)
    return failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--hook", action="store_true")
    parser.add_argument("--grade", metavar="DIR")
    args = parser.parse_args()

    if args.hook and not hook_relevant():
        return 0
    if args.grade:
        return 1 if grade(args.grade) else 0

    problems = check_all()
    if args.approve:
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        LOCK.write_text(json.dumps(digests(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Approved {len(digests())} files")
        return 0

    unapproved = check_lock()
    if problems or unapproved:
        lines = ["Reviewer CI found problems:"] + problems
        if unapproved:
            lines += unapproved + ["Get the user's approval for these changes before running check.py --approve."]
        print("\n".join(lines), file=sys.stderr)
        return 2 if args.hook else 1
    print("Reviewer CI passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
