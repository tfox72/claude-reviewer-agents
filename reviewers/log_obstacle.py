#!/usr/bin/env python3
"""Append one obstacle to the shared reviewer log. Standard library only."""
import argparse
import datetime
import pathlib
import re
import sys

LOG = pathlib.Path.home() / ".claude" / "reviewers" / "OBSTACLES.md"
MAX_FIELD = 300


def clean(text):
    """Collapse a field to one short line so an entry cannot break the log format."""
    text = re.sub(r"\s+", " ", text).replace("|", "/").strip()
    return text[:MAX_FIELD]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--kind", choices=["workaround", "proposal"], required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--workaround", default="none")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fields = [args.reviewer, args.kind, args.step, args.problem, args.workaround]
    reviewer, kind, step, problem, workaround = [clean(f) for f in fields]
    if not all([reviewer, step, problem]):
        sys.exit("reviewer, step, and problem must not be empty")

    existing = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    key = f"| {step.lower()} | {problem.lower()[:80]}"
    if key in existing.lower():
        print("Already logged")
        return

    date = datetime.date.today().isoformat()
    entry = f"- {date} | {reviewer} | {kind} | {step} | {problem} | {workaround}\n"
    if args.dry_run:
        print(entry, end="")
        return
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    print("Logged")


if __name__ == "__main__":
    main()
