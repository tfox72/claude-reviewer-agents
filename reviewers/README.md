# Reviewer system

Seven read-only review agents in `~/.claude/agents/` share the grading rules in `STANDARD.md`.

| Work | Reviewer |
|---|---|
| Code, including HTML and CSS as source | `code-reviewer` |
| Websites as people see and use them | `web-reviewer` |
| Dashboards, Power BI, charts | `dataviz-reviewer` |
| Excel and financial models | `spreadsheet-reviewer` |
| Decks, documents, writing | `document-reviewer` |
| Anything else | `independent-reviewer` |
| Final check on anything going public or to an outside audience | `prepublication-reviewer` |

When work spans two areas it gets both reviewers, and the lower score decides.

On REVISE, `fixer` applies the report's blockers, unless the fix is one or two small edits. It never grades, never invents real data, and never games the review. A fresh reviewer always checks the result.

The loop runs on its own below 8.0, with a check-in every fourth round so it cannot run up a large bill unnoticed. At 8.0 or higher you get a notification and choose: continue to 9.0, or stop with a briefing. It also stops and asks you if it needs something only you can provide, if a blocker survives two rounds, or if two rounds in a row fail to beat the best earlier score. `STANDARD.md` has the full rules.

## Keeping it healthy

- **Obstacles:** reviewers add tool problems to `OBSTACLES.md` and read it before each review. `proposal` entries are suggestions for you to accept or ignore.
- **Fast check:** `ci/check.py` validates every agent file, the standard, and the approval lock. A hook runs it whenever a reviewer file is edited, and compares the lock after every shell command.
- **Approving a change:** the grading rules, agent instructions, CI script, answer key, and test files are locked. After you agree to a change, run `ci/check.py --approve`.
- **Report check:** `ci/check.py --validate <report>` confirms a report is complete and that its verdict, score, rubric, and blockers agree. Reviewers run it on their own report, and the parent runs it again.
- **Tamper check:** `ci/check.py --snapshot <path>` fingerprints the work. The parent runs it before and after each review to confirm the reviewer changed nothing.
- **Full test:** ask Claude to "run the reviewer CI". It stages the test files with `ci/stage_fixtures.py`, sends each to its reviewer with the `ask` from `ci/manifest.json`, copies each report to `<id>.md`, and runs `ci/check.py --grade <dir>`. Each reviewer must fail its planted-error file and find every planted error. The known-good file must score at least `min_good_score`, which shows the reviewer is not failing sound work. This costs real tokens, so run it after changing instructions, not routinely.
