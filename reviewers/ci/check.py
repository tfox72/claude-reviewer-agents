#!/usr/bin/env python3
"""Checks for the reviewer agents.

  check.py                 validate agent files, the standard, fixtures, and the approval lock
  check.py --approve       record the current instructions as approved (user decision only)
  check.py --hook          PostToolUse hook: report unapproved changes to locked files
  check.py --grade D       score saved fixture reports in directory D against the manifest
  check.py --validate R    check that review report R is complete and its numbers agree
  check.py --rubric R      print the criteria and weights from report R, without scores
  check.py --snapshot P..  print a fingerprint of the work at the given paths
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from decimal import ROUND_DOWN, Decimal

HOME = pathlib.Path.home()
AGENTS = HOME / ".claude" / "agents"
ROOT = HOME / ".claude" / "reviewers"
CI = ROOT / "ci"
STANDARD = ROOT / "STANDARD.md"
LOCK = CI / "approved.lock"
MANIFEST = CI / "manifest.json"
GOOD = CI / "known_good"
SEEN = CI / ".hook_seen"
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
    "Round check-in. Stop, notify the user",
    "Never describe stopped work as passed",
    "Score history:",
    "Do not open the prior report yet",
    "check.py --validate",
    "check.py --snapshot",
]
REPORT_SECTIONS = [
    "Rubric",
    "Verified",
    "Not verified",
    "Blockers",
    "Polish",
    "What is strong",
    "Also needs",
    "Obstacles logged",
    "Next step for the parent",
]
CACHE_NAMES = {"__pycache__", ".pytest_cache", ".git", ".DS_Store"}


def walk(path):
    """Yield the files under path in a stable order, skipping caches."""
    path = pathlib.Path(path)
    if path.is_file():
        yield path
        return
    for item in sorted(path.rglob("*")):
        if item.is_file() and not set(item.relative_to(path).parts) & CACHE_NAMES and item.suffix != ".pyc":
            yield item


def locked_files():
    files = [STANDARD, FIXER] + [AGENTS / f"{name}.md" for name in REVIEWERS]
    files += [CI / "check.py", MANIFEST, CI / "stage_fixtures.py", ROOT / "log_obstacle.py"]
    return files + (list(walk(GOOD)) if GOOD.exists() else [])


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
            for pattern in fixture.get("must_find", {}).values():
                re.compile(pattern)
            if fixture.get("expect") == "good":
                float(manifest["min_good_score"])
                if not (GOOD / fixture["id"]).is_dir():
                    problems.append(f"manifest: known-good files are missing for {fixture['id']}")
            elif not fixture.get("must_find"):
                problems.append(f"manifest: {fixture['id']} has no planted errors to find")
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


def report_problems(problems, unapproved, hook=False):
    """Print what is wrong and return the exit code."""
    if not (problems or unapproved):
        if not hook:
            print("Reviewer CI passed")
        return 0
    lines = ["Reviewer CI found problems:"] + problems
    if unapproved:
        lines += unapproved + ["Get the user's approval for these changes before running check.py --approve."]
    print("\n".join(lines), file=sys.stderr)
    return 2 if hook else 1


def lock_state():
    return hashlib.sha256(json.dumps(digests(), sort_keys=True).encode()).hexdigest()


def remember(state):
    """Record the last change reported by the hook, so the same one is not repeated."""
    try:
        if state is None:
            SEEN.unlink(missing_ok=True)
        else:
            SEEN.write_text(state, encoding="utf-8")
    except OSError:
        pass


def hook():
    """Run after a tool call. A file tool gets the full check; any other tool gets the lock check."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    raw = payload.get("tool_input", {}).get("file_path", "")
    if raw:
        path = pathlib.Path(raw)
        if path == ROOT / "OBSTACLES.md" or not (ROOT in path.parents or path in locked_files()):
            return 0
        unapproved = check_lock()
        remember(lock_state() if unapproved else None)
        return report_problems(check_all(), unapproved, hook=True)

    # A shell command can change a locked file without the file tools, so compare the lock
    # after every one. Each distinct change is reported once.
    unapproved = check_lock()
    if not unapproved:
        remember(None)
        return 0
    state = lock_state()
    try:
        if SEEN.read_text(encoding="utf-8") == state:
            return 0
    except OSError:
        pass
    remember(state)
    return report_problems([], unapproved, hook=True)


def section(report, heading):
    match = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", report, re.M | re.S)
    return match.group(1) if match else None


def rubric_rows(report):
    """Return (criterion, weight, score) for each row of the rubric table."""
    rows = []
    for line in (section(report, "Rubric") or "").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        weight = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", cells[1])
        score = re.match(r"\d+(?:\.\d+)?", cells[2])
        if weight and score:
            rows.append((cells[0], Decimal(weight.group(1)), Decimal(score.group(0))))
    return rows


def validate(path):
    """Return the problems in a review report: missing parts, or numbers that disagree."""
    try:
        report = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as err:
        return [f"cannot read the report: {err}"]

    title = re.search(r"^# Independent Review: .+\(Round (\d+)\)\s*$", report, re.M)
    verdict = re.search(r"^VERDICT:\s*(PASS|REVISE|ESCALATE)\s*$", report, re.M)
    score = re.search(r"^SCORE:\s*(\d+(?:\.\d+)?)\s*/\s*10", report, re.M)
    history = re.search(r"^Score history:\s*(.+)$", report, re.M)
    reviewer = re.search(r"^Reviewer:\s*([\w-]+)\s*$", report, re.M)

    problems = []
    if not title:
        problems.append('title line must read "# Independent Review: <work>  (Round N)"')
    if not reviewer or reviewer.group(1) not in REVIEWERS:
        problems.append("Reviewer line is missing or does not name a reviewer agent")
    if not verdict:
        problems.append("VERDICT line must be exactly PASS, REVISE, or ESCALATE")
    if not score:
        problems.append("SCORE line must read X.X / 10")
    if not verdict or not score:
        return problems
    verdict, value = verdict.group(1), Decimal(score.group(1))
    round_number = int(title.group(1)) if title else 1

    scores = re.findall(r"\d+(?:\.\d+)?", history.group(1)) if history else []
    if not scores:
        problems.append("Score history line is missing")
    elif Decimal(scores[-1]) != value:
        problems.append(f"Score history ends with {scores[-1]} but the score is {value}")
    elif title and len(scores) != round_number:
        problems.append(f"Score history has {len(scores)} scores for round {round_number}; list one per round")

    wanted = REPORT_SECTIONS + (["Prior findings"] if round_number > 1 else [])
    problems += [f"section is missing: {name}" for name in wanted if section(report, name) is None]

    rows = rubric_rows(report)
    if not 4 <= len(rows) <= 6:
        problems.append(f"rubric must have 4 to 6 criteria with a weight and a score, found {len(rows)}")
    elif sum(weight for _, weight, _ in rows) != 100:
        problems.append(f"rubric weights total {sum(weight for _, weight, _ in rows)}%, not 100%")
    else:
        average = (sum(weight * points for _, weight, points in rows) / 100).quantize(Decimal("0.1"), rounding=ROUND_DOWN)
        stated = re.search(r"Weighted average:\s*(\d+(?:\.\d+)?)", report)
        if not stated or Decimal(stated.group(1)) != average:
            problems.append(f"weighted average is stated as {stated.group(1) if stated else 'nothing'} but the rubric gives {average}")
        if value > average:
            problems.append(f"score {value} is above the weighted average {average}")
        if value > Decimal("8.5") and any(points < 8 for _, _, points in rows):
            problems.append(f"a criterion scores below 8, so the score cannot be above 8.5; it is {value}")

    blockers = section(report, "Blockers") or ""
    has_blockers = bool(re.search(r"^\s*\d+[.)]\s+\S", blockers, re.M))
    if not has_blockers and not re.search(r"\bnone\b", blockers, re.I):
        problems.append('Blockers section must list numbered blockers or say "None"')
    if has_blockers and value > Decimal("8.9"):
        problems.append(f"a blocker is open, so the score cannot be above 8.9; it is {value}")
    if verdict == "PASS" and (has_blockers or value < 9):
        problems.append("PASS requires 9.0 or higher and no blockers")
    if verdict == "REVISE" and value >= 9:
        problems.append("REVISE requires a score below 9.0")
    if verdict == "REVISE" and not has_blockers:
        problems.append("REVISE needs at least one blocker to fix; use ESCALATE when only the user can close the gap")
    return problems


def print_rubric(path):
    try:
        rows = rubric_rows(pathlib.Path(path).read_text(encoding="utf-8"))
    except OSError as err:
        print(f"cannot read the report: {err}", file=sys.stderr)
        return 1
    if not rows:
        print("No rubric found in that report", file=sys.stderr)
        return 1
    print("Criteria and weights from the previous round (scores withheld):")
    for name, weight, _ in rows:
        print(f"- {name}: {weight}%")
    return 0


def snapshot(paths):
    """Print one fingerprint for all files under the given paths, ignoring caches."""
    digest = hashlib.sha256()
    count = 0
    for raw in paths:
        root = pathlib.Path(raw).expanduser().resolve()
        if not root.exists():
            print(f"not found: {raw}", file=sys.stderr)
            return 1
        for item in walk(root):
            name = item.name if root.is_file() else str(item.relative_to(root))
            digest.update(name.encode("utf-8") + b"\0" + item.read_bytes() + b"\0")
            count += 1
    print(f"{digest.hexdigest()}  {count} files")
    return 0


def grade(directory):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    limit = manifest["max_score"]
    floor = manifest.get("min_good_score")
    failed = 0
    for fixture in manifest["fixtures"]:
        good = fixture.get("expect") == "good"
        report_path = pathlib.Path(directory) / f"{fixture['id']}.md"
        issues = []
        seen = ""
        if not report_path.exists():
            issues.append("report missing")
        else:
            report = report_path.read_text(encoding="utf-8")
            verdict = re.search(r"^VERDICT:\s*(\w+)", report, re.M)
            score = re.search(r"^SCORE:\s*([\d.]+)", report, re.M)
            reviewer = re.search(r"^Reviewer:\s*([\w-]+)", report, re.M)
            seen = f"{verdict.group(1) if verdict else 'no verdict'} {score.group(1) if score else 'no score'}"
            if good:
                if not score or float(score.group(1)) < floor:
                    issues.append(f"known-good work scored {score.group(1) if score else 'missing'}, expected at least {floor}")
            else:
                if not verdict or verdict.group(1) == "PASS":
                    issues.append(f"verdict was {verdict.group(1) if verdict else 'missing'}")
                if not score or float(score.group(1)) > limit:
                    issues.append(f"score was {score.group(1) if score else 'missing'}, limit {limit}")
            if not reviewer or reviewer.group(1) != fixture["reviewer"]:
                issues.append(f"reviewer line was {reviewer.group(1) if reviewer else 'missing'}")
            issues += [
                f"missed planted error: {label}"
                for label, pattern in fixture.get("must_find", {}).items()
                if not re.search(pattern, report, re.I | re.S)
            ]
            issues += [f"report format: {problem}" for problem in validate(report_path)]
        kind = "good" if good else "planted"
        print(f"{fixture['id']:<10} {kind:<8} {'PASS' if not issues else 'FAIL'}  {seen:<14} {'; '.join(issues)}")
        failed += bool(issues)
    return failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--hook", action="store_true")
    parser.add_argument("--grade", metavar="DIR")
    parser.add_argument("--validate", metavar="REPORT")
    parser.add_argument("--rubric", metavar="REPORT")
    parser.add_argument("--snapshot", metavar="PATH", nargs="+")
    args = parser.parse_args()

    if args.hook:
        return hook()
    if args.grade:
        return 1 if grade(args.grade) else 0
    if args.validate:
        problems = validate(args.validate)
        print("\n".join(["Report has problems:"] + problems) if problems else "Report is valid")
        return 1 if problems else 0
    if args.rubric:
        return print_rubric(args.rubric)
    if args.snapshot:
        return snapshot(args.snapshot)

    problems = check_all()
    if args.approve:
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        LOCK.write_text(json.dumps(digests(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        remember(None)
        print(f"Approved {len(digests())} files")
        return 0
    return report_problems(problems, check_lock())


if __name__ == "__main__":
    sys.exit(main())
