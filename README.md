# Claude Code reviewer agents

Independent subagents for Claude Code that grade finished work against a 9/10 bar, plus one shared fixer. Reviewers are read-only, so the agent that grades the work never changes it.

| Work | Agent |
|---|---|
| Code, including HTML and CSS as source | `code-reviewer` |
| Websites as people see and use them | `web-reviewer` |
| Dashboards, Power BI, charts | `dataviz-reviewer` |
| Excel and financial models | `spreadsheet-reviewer` |
| Decks, documents, writing | `document-reviewer` |
| Anything else | `independent-reviewer` |
| Final check on anything going to an outside audience | `prepublication-reviewer` |
| Applies the blockers from a review | `fixer` |

## How the loop works

The main Claude Code session runs the loop, because subagents cannot launch subagents.

- **Below 8.0:** the fixer and a fresh reviewer keep going without asking, with a check-in every fourth round so the loop cannot run up a large bill unnoticed.
- **At 8.0 to 8.9:** the session notifies you and asks whether to continue to 9.0 or stop with a briefing.
- **PASS:** 9.0 or higher, with no open blockers and no caps triggered.
- **Early stops:** the loop asks you if it needs something only you can provide, if a blocker survives two rounds, or if two rounds in a row fail to beat the best earlier score.
- **Every round:** the session fingerprints the work before and after the review to confirm the reviewer changed nothing, and validates the report before acting on it.
- **Re-reviews:** a later reviewer reuses the earlier criteria and weights, and grades before it opens the earlier report, so the previous score cannot anchor it.

The grading rules are in [`reviewers/STANDARD.md`](reviewers/STANDARD.md).

## Install

Requires Claude Code and Python 3 with PyYAML. The planted-error fixtures also need `openpyxl` and `python-pptx`.

```bash
git clone https://github.com/tfox72/claude-reviewer-agents.git
```

```bash
mkdir -p ~/.claude/agents ~/.claude/reviewers && cp claude-reviewer-agents/agents/*.md ~/.claude/agents/ && cp -R claude-reviewer-agents/reviewers/. ~/.claude/reviewers/
```

```bash
python3 ~/.claude/reviewers/ci/check.py
```

New agents register between turns, so start a new session after installing.

### Route work to the reviewers

Add this to your `~/.claude/CLAUDE.md` so sessions use the reviewers automatically:

```markdown
## Independent review
Before telling me a finished deliverable is done, send it to the matching reviewer agent with my original ask and no opinion of the work:
- Code, including HTML and CSS as source -> code-reviewer
- Websites as people see and use them -> web-reviewer
- Dashboards, Power BI, charts -> dataviz-reviewer
- Excel and financial models -> spreadsheet-reviewer
- Decks, documents, writing -> document-reviewer
- Anything else -> independent-reviewer
If work spans two areas, use both; the lower score decides. The bar is 9/10. Below 8.0, keep fixing and sending fresh reviews with the prior report, without asking, apart from a check-in every fourth round. At 8.0 or higher, notify me and ask whether to continue to 9.0 or stop with a briefing. The full loop is in ~/.claude/reviewers/STANDARD.md. Report only the score the reviewer gave. Review finished deliverables only, not every edit or small tweak.
For anything going public or to an outside audience, run prepublication-reviewer as the last check after the specialist passes; it is not needed for internal drafts.
On REVISE, send the report and my original ask to the fixer agent, unless the fix is one or two small edits, then send the result to a fresh reviewer. Anything the fixer cannot finish without my input comes to me.
```

### Optional: check edits automatically

Add this to the `PostToolUse` hooks in `~/.claude/settings.json`. It validates reviewer files whenever one is edited. Add a second copy with the matcher `Bash` to compare the lock after every shell command, since a shell command can change a file without the file tools:

```json
{
  "matcher": "Edit|Write",
  "hooks": [
    {
      "type": "command",
      "command": "f=\"$HOME/.claude/reviewers/ci/check.py\"; [ ! -f \"$f\" ] || python3 \"$f\" --hook",
      "timeout": 15,
      "statusMessage": "Checking reviewer files"
    }
  ]
}
```

## Changing the rules

The grading rules, agent instructions, CI script, answer key, and known-good test files are locked by checksum in `reviewers/ci/approved.lock`. The lock reports changes; it relies on Claude asking you before it records an approval. After you agree to a change, record it:

```bash
python3 ~/.claude/reviewers/ci/check.py --approve
```

More detail, including the full test with planted-error files and a known-good file, is in [`reviewers/README.md`](reviewers/README.md).

## Other checks

```bash
python3 ~/.claude/reviewers/ci/check.py --validate <report.md>
```

Confirms a review report is complete and that its verdict, score, rubric, and blockers agree.

```bash
python3 ~/.claude/reviewers/ci/check.py --snapshot <path>
```

Prints a fingerprint of the work, ignoring caches.

`reviewers/OBSTACLES.md` is a running log of tool workarounds that reviewers read before each review. Its entries reflect the Mac where they were recorded.
