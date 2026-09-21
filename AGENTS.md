<!-- SDD:START -->
# SDD — Project Manager

Spec-driven development workflows. When the user invokes a `/sdd:` or `/pm:` command, read `skill/sdd/SKILL.md` and route to the matching reference doc.

## Commands

| Command | Reference | Purpose |
|---------|-----------|---------|
| `init` | skill/sdd/references/init.md | Bootstrap `.sdd/` directories and config |
| `ctx-create` | skill/sdd/references/context.md | Create initial project context docs |
| `ctx-prime` | skill/sdd/references/context.md | Load context for new session |
| `ctx-update` | skill/sdd/references/context.md | Update context to reflect current state |
| `office-hours` | skill/sdd/references/plan.md | Collaborative brainstorming session |
| `prd-rethink` | skill/sdd/references/plan.md | Challenge premises, find 10-star product |
| `prd-new` | skill/sdd/references/prd.md | Write a new PRD via guided discovery |
| `prd-validate` | skill/sdd/references/prd.md | Validate PRD completeness and coherence |
| `prd-qualify` | skill/sdd/references/prd.md | Validate/edit loop until PRD passes |
| `prd-edit` | skill/sdd/references/prd.md | Edit existing PRD with impact analysis |
| `prd-design` | skill/sdd/references/design.md | Design system, mockups, implementation specs |
| `team-build` | skill/sdd/references/doc.md | Full doc pipeline: PRD to epic |
| `epic-run` | skill/sdd/references/execute.md | Epic autopilot — plan, execute, verify tasks |
| `epic-verify` | skill/sdd/references/verify.md | Verification pipeline — semantic + integration |
| `epic-merge` | skill/sdd/references/merge.md | Merge epic branch + cleanup |
| `issue-new` | skill/sdd/references/work.md | Create a new issue |
| `issue-start` | skill/sdd/references/work.md | Start work on an issue |
| `issue-complete` | skill/sdd/references/work.md | Complete work on an issue |
| `qa:scenario-new` | skill/sdd/references/qa.md | Create QA test scenario |
| `qa:run` | skill/sdd/references/qa.md | Run QA test suite |

## Conventions

Read `skill/sdd/references/conventions.md` for frontmatter format, git branch naming, commit format, and path conventions.

## Runtime Data

All workflow state is stored in `.sdd/` (prds, epics, context, verify, config, sessions, qa, progress). Never write to `.claude/`.
<!-- SDD:END -->
