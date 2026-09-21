---
name: sdd
description: Project management workflows — plan features, write PRDs, decompose epics, execute tasks, verify quality, merge to main
version: 1.0.0
---

# SDD — Spec-Driven Development

Spec-driven development workflows. Route commands below to their reference doc.

## Commands

| Command | Reference | Purpose |
|---------|-----------|---------|
| `init` | [init.md](references/init.md) | Bootstrap `.sdd/` directories and config |
| `claude-md-refresh` | [init.md](references/init.md) | Append Karpathy section to existing CLAUDE.md |
| `ctx-create` | [context.md](references/context.md) | Create initial project context docs |
| `ctx-prime` | [context.md](references/context.md) | Load context for new session |
| `ctx-update` | [context.md](references/context.md) | Update context to reflect current state |
| `office-hours` | [plan.md](references/plan.md) | Collaborative brainstorming session |
| `plan-review` | [plan-review.md](references/plan-review.md) | Adversarial epic review — risks, weaknesses, criticals |
| `prd-rethink` | [plan.md](references/plan.md) | Challenge premises, find 10-star product |
| `prd-new` | [prd.md](references/prd.md) | Write a new PRD via guided discovery |
| `prd-validate` | [prd.md](references/prd.md) | Validate PRD completeness and coherence |
| `prd-qualify` | [prd.md](references/prd.md) | Validate/edit loop until PRD passes |
| `prd-edit` | [prd.md](references/prd.md) | Edit existing PRD with impact analysis |
| `prd-design` | [design.md](references/design.md) | Design system, mockups, implementation specs |
| `team-build` | [doc.md](references/doc.md) | Full doc pipeline: PRD to epic |
| `epic-run` | [execute.md](references/execute.md) | Epic autopilot — plan, execute, verify tasks |
| `epic-verify` | [verify.md](references/verify.md) | Verification pipeline — semantic + integration |
| `epic-merge` | [merge.md](references/merge.md) | Merge epic branch + cleanup |
| `issue-new` | [work.md](references/work.md) | Create a new issue |
| `issue-start` | [work.md](references/work.md) | Start work on an issue |
| `issue-complete` | [work.md](references/work.md) | Complete work on an issue |
| `qa:scenario-new` | [qa.md](references/qa.md) | Create QA test scenario |
| `qa:run` | [qa.md](references/qa.md) | Run QA test suite |

## Shared Rules

All references depend on [conventions.md](references/conventions.md) for:
- Frontmatter format and datetime handling
- Git branch naming and commit format
- GitHub CLI patterns and repo protection
- `.sdd/` path convention
- Error message and output format

## Sub-references

Loaded on demand by a reference doc, not routed to directly:

| File | Loaded by | Purpose |
|------|-----------|---------|
| [cognitive-lenses.md](references/cognitive-lenses.md) | [plan.md](references/plan.md) Step 0F | The 4 reframe lenses, in fixed order |

## Unknown Command

If the user's request does not match any command above:

1. List the 20 available commands with one-line descriptions
2. Suggest the closest match based on the user's intent
3. Example: "Did you mean `epic-run`? That handles automated epic execution."
