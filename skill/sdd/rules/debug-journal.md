# Debug Journal

Captures diagnostic chains (hypothesis → action → result) across debugging rounds. Persists state across compacts and session ends.

## File Locations

- **Active:** `.claude/context/sessions/issue-{N}-debug.md`
- **Archive:** `.claude/context/sessions/archive/issue-{N}-debug.md`
- On first use: `mkdir -p .claude/context/sessions/archive 2>/dev/null`
- `.claude/context/sessions/` is local-only — not committed (see `.gitignore`)

## Journal Format

### Header
```markdown
# Debug Journal: Issue #{N} — {title}
Created: {ISO timestamp}
Mode: auto | semi-auto | manual
```

### Round Entry
```markdown
## Round {N} — {ISO timestamp}
**Hypothesis:** {description}
**Action:** {what was tried}
**Result:** PASS | FAIL
**Notes:** {observations, negative learnings}
```

## Mode Behaviors

- **Auto:** Claude appends a Round entry after every fix→test cycle. No user interaction needed.
- **Semi-auto:** Claude appends a Round entry only on state changes (see triggers). Default mode.
- **Manual:** Claude prompts user at each state change: `"🔖 {state change description}. Ghi vào debug journal?"`. Only writes if user confirms.

## State Change Triggers

1. New hypothesis formed (different from previous approach)
2. Root cause identified or updated
3. Approach abandoned (decided not to pursue)
4. Fix verified PASS or FAIL

## Reading & Resuming

On session resume: if active journal exists, read it and display current state.

Resume summary format:
```
Resuming Issue #{N}. Round {last_round}. Last hypothesis: {H}. Status: {PASS/FAIL}
```

Journal is the single source of truth for debug state across sessions.
