# Delegation Protocol

When SDD commands delegate complex work to subagents, follow these patterns to prevent silent step-skipping and summarized-prompt failures.

## When to Delegate

Delegate to a subagent when:
- Context window is under pressure and a self-contained phase can run independently
- Parallel work is needed across isolated task sets (no shared file conflicts)
- A command has a clearly bounded scope (e.g., `epic-verify-a`, `epic-verify-b`)

Do not delegate when:
- The step requires real-time decisions fed back to the orchestrator
- Output of the delegated step is immediately needed to continue the current flow

## Prompt Construction

**CRITICAL:** Always point subagents to the command file. Never summarize command content.

### Always include

```
Read and follow `skill/sdd/references/{reference}.md` section `{section}` and execute ALL steps exactly as written.
Do NOT skip, summarize, or reinterpret any section.
```

When a command has sub-steps (e.g., epic-verify calls epic-verify-a.md and epic-verify-b.md), list all paths explicitly:

```
Execute in order:
1. Read and follow `skill/sdd/references/verify.md` section `epic-verify-a` — execute ALL steps
2. Read and follow `skill/sdd/references/verify.md` section `epic-verify-b` — execute ALL steps
```

### Never do

- Never write your own paraphrase of the command in the prompt
- Never drop a sub-step because it "looks optional" or "seems already done"
- Never condense a multi-phase command into a single instruction sentence

## Post-Delegation Verification

After a subagent returns, verify its output before continuing:

1. **Artifacts exist** — check that expected output files were created or updated
2. **All sections present** — if the command produces a report, confirm all required sections appear
3. **No silent skips** — if a section is missing, re-delegate that specific step rather than continuing

```bash
# Example: verify epic-verify produced a full report
test -f .claude/context/progress/{epic}-verify.md || echo "❌ Verify report missing — re-run epic-verify"
grep -q "QA Tier" .claude/context/progress/{epic}-verify.md || echo "❌ QA section missing — subagent skipped a step"
```

## Anti-Patterns

| Anti-Pattern | Example | Why It Fails |
|---|---|---|
| **Summarized prompt** | "Run epic-verify: check tests pass, linting ok, and write a summary" | Agent invents its own checklist; real command steps are skipped |
| **Skipped sub-steps** | Delegate only `epic-verify-a.md`, omit `epic-verify-b.md` | QA tier or other phases silently dropped |
| **Prompt-based shortcut** | "Verify the epic is complete" | No command file reference; agent guesses scope |
| **Assumed completion** | Continue after delegation without checking output artifacts | Silent failures propagate undetected |

## Examples

### Good delegation prompt

```
Read and follow `skill/sdd/references/verify.md` section `epic-verify` and execute ALL steps exactly as written.
Epic name: my-feature
Do NOT skip, summarize, or reinterpret any section.
After completion, confirm: (1) verify report written, (2) all sections present.
```

### Bad delegation prompt

```
Run verification for the my-feature epic. Check that tests pass, code quality is good,
and write a short summary of findings.
```

This is bad because: it omits the command file path, the agent will invent its own verification steps, and entire phases (e.g., QA tier review) will be silently skipped.
