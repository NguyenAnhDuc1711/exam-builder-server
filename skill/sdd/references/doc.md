# Documentation Pipeline

Full PRD-to-epic pipeline: `prd-new` → `prd-qualify` → [`prd-design`] → `prd-parse` → `plan-review` → `decompose` → `epic-sync` → `epic-start` → `epic-run` → `epic-verify` → `epic-merge`.

PRD authoring commands (`prd-new`, `prd-validate`, `prd-qualify`, `prd-edit`) are in [prd.md](prd.md).
Design pipeline (`prd-design`) is in [design.md](design.md).

See [conventions.md](conventions.md) for shared rules (frontmatter, paths, git, GitHub ops).

## team-build

Orchestrates the full pipeline with gates and agent delegation. Primary entry point for shipping features.

### Usage

```
team-build <feature-name> [--resume] [--dry-run] [--no-gate=<gate>]
```

- `--resume` — continue from last saved state
- `--dry-run` — show planned steps with gate positions; does NOT execute
- `--no-gate=<gate>` — auto-execute gate step without confirmation (step still runs, only prompt is bypassed; repeatable)

### Pipeline Flow

```
prd-new → prd-qualify(validate↔edit loop) → prd-parse → plan-review → decompose → epic-sync → epic-start → epic-run → epic-verify → epic-merge
```

10 steps, 4 mandatory gates (prd-new, plan-review, epic-run, epic-merge). State persists via `scripts/pm/build-state.sh` — safe to interrupt and resume.

### Step Table

| # | Step | Gate | Tier | Model | Reference |
|---|------|------|------|-------|-----------|
| 1 | prd-new | YES | heavy | opus | [prd.md](prd.md) |
| 2 | prd-qualify | no (loop) | heavy | opus | [prd.md](prd.md) |
| 3 | prd-parse | no | heavy | opus | below |
| 4 | plan-review | YES | heavy | opus | [plan.md](plan.md) |
| 5 | decompose | no | heavy | opus | below |
| 6 | epic-sync | no | medium | sonnet | below (inline) |
| 7 | epic-start | no | medium | sonnet | below (inline) |
| 8 | epic-run | YES | heavy | opus | [execute.md](execute.md) — orchestrator: dispatches sub-agents per task |
| 9 | epic-verify | no | medium | sonnet | [verify.md](verify.md) |
| 10 | epic-merge | YES | medium | sonnet | [merge.md](merge.md) |

### Agent Orchestration

#### Team Setup

Before any Agent calls, create the team (required for teammate panels):

```bash
rm -rf ~/.claude/teams/build-{feature} ~/.claude/tasks/build-{feature} 2>/dev/null
```

```
TeamCreate(team_name="build-{feature}", description="Build pipeline for {feature}")
```

#### Agent Spawn Template

Every step spawns a **teammate** with these exact parameters:

```
Agent(
  description="Execute {step-name}",
  prompt="Read and follow `skill/sdd/references/{reference}` section `{section}` and execute ALL steps exactly as written.
    Do NOT skip, summarize, or reinterpret any section.
    Feature/epic name: {feature}
    After completion, return a concise summary (max 200 words): status, artifacts created, any warnings.",
  team_name="build-{feature}",
  name="step-{N}-{step-name}",
  model="{model from Step Table}"
)
```

- `{model}` — look up from Step Table (opus/sonnet). **ALWAYS pass explicitly.**
- `{reference}` and `{section}` — look up from Step Table's Reference column
- Do NOT use `subagent_type` — teammates don't use it

#### Teammate Lifecycle

After each step's agent returns:
1. Verify artifact exists (see Artifact Detection below)
2. `SendMessage(to="step-{N}-{step-name}", message={type: "shutdown_request"})` — graceful shutdown
3. Next step spawns a fresh teammate — avoids stale surface references

### Artifact Detection (Skip Completed Steps)

Before executing each step, check if its output artifact already exists. If so, skip and advance state.

| Step | Artifact Check | Pass Condition |
|------|---------------|----------------|
| prd-new | PRD file | `.sdd/prds/{feature}.md` exists |
| prd-qualify | PRD validated | PRD frontmatter `status: validated` AND `.sdd/prds/.validation-{feature}.md` has `status: passed` |
| prd-parse | Epic file | `.sdd/epics/{feature}/epic.md` exists |
| plan-review | Review file | `.sdd/epics/{feature}/plan-review.md` exists AND `verdict:` is NOT `blocked` |
| decompose | Task files | `[0-9]*.md` files exist in `.sdd/epics/{feature}/` |
| epic-sync | GitHub linked | Epic frontmatter `github` field is non-empty |
| epic-start | Branch exists | Current git branch is `epic/{feature}` |
| epic-run | Tasks closed | All tasks in epic have `status: closed` |
| epic-verify | Report exists | Verify report exists AND contains `## .*QA.*Results` section |
| epic-merge | Epic done | Epic frontmatter has `status: completed` |

For each step from current index to end: run artifact check, if present log `[N/10] skip {step}` and advance state.

### Gate Display Format

At gate steps, display and wait for user input (unless `--no-gate` suppresses the prompt):

```
===================================
GATE: {step-name}
===================================
Completed: {list of completed steps}
Next: {current step} -> {remaining steps}

Proceed? (yes / skip / abort)
```

- **yes** — spawn agent to execute the step
- **skip** — advance state without execution
- **abort** — save state, display progress, exit

`--no-gate` is equivalent to auto-answering "yes" — the step still executes, only the prompt is bypassed.

**Step 8 special handling (epic-run):** epic-run is an orchestrator step — it must be spawned with full agent dispatch capability (not run inline). When spawning this step, use `subagent_type: general-purpose` and `model="opus"` with the prompt: `sdd epic-run {feature}`. epic-run will read task files, group parallel/sequential tasks, and dispatch sub-agents per task with each task's `recommended_model` — identical to running `sdd epic-run {feature}` standalone. Do NOT inline epic-run's task execution; always delegate to epic-run as the orchestrator.

### Error Handling

**Transient vs permanent errors:** After an agent returns, if the expected artifact is missing, inspect the result for transient keywords (`network`, `rate limit`, `timeout`, `ECONNREFUSED`, `lock`). Transient errors get one automatic retry with a fresh agent. If retry also fails (or error is non-transient), show the failure menu:

```
[N/10] FAIL {step-name} — {error summary}

Options:
  fix:   Fix the issue, then resume (team-build {feature} --resume)
  skip:  Skip this step and continue
  abort: Stop the build
```

- **fix** — save state, clean up team, exit (user resumes via `--resume`)
- **skip** — advance state, continue to next step
- **abort** — save state, clean up team, exit with summary

### Plan-Review Apply (Between Steps 4 and 5)

After plan-review completes, apply its findings to `epic.md` before decompose. Orchestrator handles this directly (no agent needed).

1. Read `plan-review.md` frontmatter: `verdict`, `critical_gaps`, `warnings`.
2. If `verdict: blocked` — show critical issues, offer fix/skip/abort menu.
3. If `verdict: ready` with 0 issues — skip apply, proceed to decompose.
4. If warnings exist — read full review, apply recommended changes (ADR corrections, task adjustments, risk additions, dependency updates) to `epic.md`.
5. Hash-compare `epic.md` before/after. If unchanged despite warnings, offer proceed/retry menu.

→ See execute.md §epic-sync

→ See execute.md §epic-start

### Completion Summary

After all 10 steps (or on abort), display a table with step name, status, and duration for each step. Show total time, steps completed, and next action (celebrate or `--resume` command).

If running without orchestration, execute each section below in order.

---

## prd-parse

Convert PRD into a technical implementation epic.

### Preflight

1. Validate feature name (kebab-case).
2. `.sdd/prds/{feature}.md` must exist with frontmatter + Executive Summary + Problem Statement + Requirements.
3. Check requirement format: if no `FR-N`/`NFR-N` IDs, warn and auto-assign.
4. If `.sdd/epics/{feature}/epic.md` exists, ask: overwrite?
5. Check overlap with active epics (scan `.sdd/epics/*/epic.md`).
6. `mkdir -p .sdd/epics/{feature} 2>/dev/null`

### Role

Principal engineer translating product vision into technical plans. Five lenses: Simplicity, Risk, Reuse, Regret, Parallelism.

### Analysis

For each requirement: simplest implementation? Edge cases? Conflicts? Reuse opportunities? Testing strategy?

**Extract and organize:**
- Requirement IDs → Traceability Matrix (use PRD's exact IDs, or assign if missing)
- Personas → UX/API design decisions
- MUST vs NTH → NTH may become follow-up epic
- Risks → carry forward into technical assessment
- Success Criteria → map to verifiable checks

If ambiguities affect architecture, ask user (max 5 questions, group in one message). Offer to proceed with best judgment if preferred.

### Epic Structure

Save to `.sdd/epics/{feature}/epic.md` with sections:

**Overview:** Why this approach, not just what. 3-5 sentences with architectural reasoning.

**Architecture Decisions (ADR format):**
```
### AD-N: [Title]
Context: [situation requiring decision]
Decision: [what we chose]
Alternatives rejected: [what and why not]
Trade-off: [gain vs lose]
Reversibility: [Easy/Hard]
```

**Technical Approach:** Specific implementation per component — file paths, existing patterns, integration points.

**Traceability Matrix:**

| PRD Requirement | Epic Coverage | Task(s) | Verification |
|-----------------|--------------|---------|-------------|
| FR-1: [name] | §section | T1, T3 | Unit test |
| NTH-1: [name] | Deferred | — | — |

Every MUST requirement maps to at least one task. NTH deferred explicitly.

**Implementation Strategy:** Phase 1 (foundation, critical path) → Phase 2 (core, parallelizable) → Phase 3 (polish, integration). Each phase: what, why, exit criterion.

**Task Breakdown (enriched preview):**
```
##### T{N}: [name]
- Phase: {N} | Parallel: yes/no | Est: {N}d | Depends: — | Complexity: simple|moderate|complex
- What: [2-3 sentences — specific approach, file paths, patterns]
- Key files: [paths]
- PRD requirements: [FR-IDs]
- Key risk: [1 sentence]
- Interface receives from T{X}: [what this expects from dependency]
- Interface produces: [what downstream consumes]
```

Rules: ≤10 tasks, each 1-3 days. Every MUST requirement in at least one task.

**Risks:** ≥3 entries with severity, likelihood, impact, mitigation. Carry forward from PRD + add technical risks.

**Success Criteria (Technical):** Map PRD criteria to technical metrics with targets and measurement methods.

### Quality Checks

- **Traceability:** Every MUST requirement appears in Traceability Matrix with at least one task mapping. NTH requirements explicitly marked as deferred.
- **ADRs:** Each has Context, Decision, Alternatives rejected (with why), Trade-off, Reversibility rating.
- **Task count:** 10 or fewer tasks total. Each sized 1-3 days.
- **Conflict detection:** No parallel tasks touching the same files (check `conflicts_with` and `files` fields).
- **Risk coverage:** At least 3 risks with severity, likelihood, impact, mitigation. Must include both PRD-carried and technical risks.
- **Phase structure:** Tasks organized into phases with clear exit criteria per phase.
- **Interface contracts:** Tasks with dependencies specify exactly what they receive and produce.
- **Success criteria mapping:** Every PRD success criterion maps to a technical metric with target and measurement method.

### Model Tier

Requires `opus` — architecture decisions, traceability analysis, risk assessment.

---

## decompose

Break epic into concrete, actionable task files.

### Preflight

1. `.sdd/epics/{feature}/epic.md` must exist with Overview, Technical Approach, Task Breakdown.
2. If task files already exist, ask: delete and recreate?

### Task Design Principles

Each task MUST be:
- **Self-contained:** engineer can start without reading the epic
- **Testable independently:** AC verifiable without other tasks
- **Sized right:** 1-3 days (larger → break down; <4 hours → combine)
- **Ordered logically:** foundation → features (parallel) → integration
- **Traceable:** maps to PRD requirement(s) via traceability matrix
- **Interface-explicit:** tasks with dependencies specify exactly what they receive/produce

### Complexity Scoring

| Signal | Simple | Moderate | Complex |
|--------|--------|----------|---------|
| Files touched | 1-2 | 3-5 | 6+ |
| Days | <1d | 1-2d | 3d+ |
| Dependencies | None | 1-2 | 3+ or external |
| Nature | Config, docs | New feature | Refactor, architecture |

Model mapping: simple/moderate → `sonnet`, complex → `opus`. When borderline, classify UP.

### Numbering (Gap Strategy)

```
Phase 1: 001.md, 002.md, 003.md     (foundation)
Phase 2: 010.md, 011.md, 012.md     (core features)
Phase 3: 020.md, 021.md             (polish)
Final:   090.md                      (verification — always last)
```

Gaps allow future insertions without renumbering.

### Task File Format

Each task at `.sdd/epics/{feature}/{number}.md`:

**Frontmatter:** name, status (`open`), created, updated, complexity, recommended_model, phase, priority, depends_on, parallel, conflicts_with, files, prd_requirements.

**Required sections:**
- **Context:** WHY this task exists (without needing epic knowledge)
- **Description:** specific approach with real file paths
- **Implementation Steps:** concrete code-level actions with paths, functions, logic
- **Acceptance Criteria:** scenario-linked: `**FR-N / scenario:** [condition]`
- **Interface Contract** (if depends_on non-empty): what it receives and produces
- **Tests to Write:** concrete test cases per AC
- **Technical Details:** reference actual code, patterns
- **Verification Checklist:** concrete commands to run

**Anchor Code** (complex tasks only): pseudocode skeleton.

### Content Quality Standards

- Context: explains WHY without epic knowledge
- Description: references real file paths and existing patterns
- AC: uses `**FR-N / scenario:**` format with specific thresholds
- Implementation Steps: ≥2 steps with file paths and logic
- Tests: ≥1 concrete test case per AC
- Verification: concrete commands, not "run tests"

### Mandatory Verification Task (090.md)

Every epic MUST include a final verification task:
- Depends on ALL other tasks
- Checks: all tasks done, build succeeds, all tests pass, epic-specific integration checks
- Specific commands to run for verification

### Post-Decompose

1. Update epic with: Tasks Created table, dependency graph, PRD Coverage table
2. Confirm count, parallel ratio, critical path, PRD coverage

### Model Tier

Requires `opus` — task decomposition demands judgment on sizing, dependencies, and interface contracts.

---

→ See conventions.md §Sandbox
