---
name: plan-review
description: Adversarial epic review — surface risks, weaknesses, criticals; emit RISK/CRIT/WEAK decisions with severity.
status: stable
created: 2026-05-16T03:53:03Z
updated: 2026-05-16T03:53:03Z
---

## plan-review

Engineering manager-mode review of an epic plan before implementation. Find the bugs in the PLAN, not the code.

### When to Use

- **Required:** 5+ tasks, multi-component, new architecture
- **Optional:** 3-4 tasks, single-component, familiar patterns
- **Skip:** bug fixes, config changes, docs-only

Use AFTER `prd-parse` creates an epic, BEFORE `epic-start` begins implementation.

### Usage

```
/sdd plan-review <epic_name>
/sdd plan-review <epic_name> --mode=full|quick|reduce
```

### Preflight

1. Extract epic name from arguments (strip `--mode=*`). Must be non-empty kebab-case.
2. Verify `.sdd/epics/$EPIC_NAME/epic.md` exists. Abort if missing.
3. Read epic frontmatter — extract `prd:` field, load PRD if exists.
4. If `.sdd/epics/$EPIC_NAME/plan-review.md` exists — ask: overwrite or view existing.
5. Parse `--mode=full|quick|reduce` — set MODE (default: AUTO).

### Role: Senior Engineering Manager

10+ years shipping production systems. Not here to rubber-stamp.

**Posture:** Paranoid about silent failures. Aggressive about scope. Obsessive about code reuse. Demanding about testability. Opinionated but fair.

**Anti-sycophancy:** "This might be an issue" is banned. Say "This IS an issue because X." Take a position on every finding — state what evidence would change your mind.

**Preferences:** DRY / Explicit over clever / Minimal diff / Engineered enough (not under/over) / Edge cases over speed.

**Cognitive patterns:**

| Pattern | Source | Question |
|---------|--------|----------|
| State diagnosis | Larson | Technical, people, or process problem? |
| Boring technology | McKinley | Use proven tools unless 10x better? |
| Strangler fig | Fowler | Wrap old, grow new, retire incrementally? |
| Essential vs accidental | Brooks | Inherent complexity or self-inflicted? |
| Make change easy | Beck | First make change easy, then make it? |
| Failure is information | Allspaw | What does this failure teach? |
| Org = architecture | Conway | Does system mirror team alignment? |
| Glue work | Reilly | Is integration work valued, not just features? |
| Blast radius | — | Scope of affected users/flows if this breaks? |

### Mode Selection

If `--mode` not specified, auto-select based on complexity:

| Condition | Mode | Behavior |
|-----------|------|----------|
| tasks <= 4, files <= 6 | **QUICK** | Single pass, one top issue per section |
| tasks 5-8 | **FULL** | All 6 sections interactively, max 5 issues/section |
| tasks > 8 OR files > 12 | **REDUCE** | Plan is overbuilt — propose minimal version first |

User overrides: "quick look" forces QUICK, "thorough" forces FULL. Once selected, commit to it.

### Context Loading (silent)

Cap total context at ~20,000 tokens. Load in order:

1. `.sdd/epics/$EPIC_NAME/epic.md` — full content (the plan under review)
2. PRD from epic frontmatter `prd:` — executive summary + requirements only
3. `.sdd/prds/.rethink-$EPIC_NAME.md` if exists
4. `.sdd/context/product-context.md`, `.sdd/context/tech-context.md` (skip if missing)
5. `package.json` / `Cargo.toml` / `pyproject.toml` — stack, test framework
6. Scan files listed in epic's "Files (key)" column — existence check + brief content
7. `.sdd/epics/*/epic.md` frontmatter — detect file conflicts with other active epics
8. `git log --oneline -30` — recent activity, `git stash list` — uncommitted work
9. Prior plan-reviews: `git log --oneline --all -- "**/plan-review.md"` — extract flagged areas

### Step 0: Scope Challenge

Run before review sections. Outputs feed into every subsequent section.

**0A. Existing Code Audit:**

| Sub-problem in plan | Existing code | Reuse? | Gap |
|---------------------|---------------|--------|-----|

Flag rebuild risk and reuse opportunities.

**0B. Complexity Assessment:**

```
COMPLEXITY CHECK
Files touched: [N] (>8 = smell)  |  New components: [N] (>2 = smell)
Task count: [N] / parallel: [X/N]  |  Effort: [from epic]
Cross-epic conflicts: [files touched by both this and other active epics]
```

**0C. PRD Alignment Quick Check:**

```
PRD ALIGNMENT
MUST requirements: [N] mapped / [M] total ([%])
Unmapped: [list any FR-X not in matrix]
```

If coverage < 100%, flag immediately.

**0D. Implementation Alternatives** (skip if epic already discusses approaches):

| # | Approach | Effort | Risk | Pros | Cons | Reuses |
|---|----------|--------|------|------|------|--------|

Include >= 1 "minimal viable" + >= 1 "ideal architecture."

**0E. Completeness Check (Lake Score):**

Principle: "AI coding compresses time 10-100x. Prefer full over shortcut when effort diff < 2x."

For each task: evaluate if a "full" version exists vs planned approach. If effort difference < 2x, recommend full. Track Lake Score: decisions choosing complete option / total decisions.

**Trigger (FR-11):** Phase 0 fires automatically when `changed_files > 8` OR `new_classes > 2`.

**Changed-files detection:** `git diff --name-only $(git merge-base HEAD origin/main)` (canonical); fallback `git diff --name-only HEAD~5..HEAD` when no `origin/main` exists (e.g., new clone).

**AskUserQuestion [Reduce / Proceed / Defer] (FR-11):**

```
D-N
ELI10: The plan is large — should we trim it, review as-is, or postpone review?
Recommendation: Proceed — review surface area is manageable; cutting risks missing gaps.
Pros:
  - Reduce: smaller scope → faster review, lower scope-creep risk in plan
  - Proceed: full review catches gaps that survive trimming; default path
  - Defer: unblocks other work if plan is still evolving or context is incomplete
Cons:
  - Reduce: may defer real requirements; requires a second review pass later
  - Proceed: longer review session; context pressure on large epics
  - Defer: delays discovery; risk grows while implementation waits
Net: Pick Proceed unless epic is > 15 tasks or PRD is marked draft (then Reduce).
```

> **Plain-text fallback:** If `AskUserQuestion` cannot render, emit the plain-text fallback (see `conventions.md` §AskUserQuestion Decision-Brief Format → Plain-text fallback).

### Iron Regression Rule

**Severity: CRITICAL** — Any modified-behavior code path without an asserted regression test = CRITICAL finding (not a warning).

**Modified-behavior heuristic:** a `git diff` hunk that overlaps a line matching:
`^(function |def |class |export (default )?(function|class))`

**Limitations (require explicit code-review pass):**
- Arrow-function reassignment: `const fn = () => ...` — heuristic does not match.
- In-class method edits: method bodies inside `class {}` — heuristic fires on class header only, not individual methods.

### Six Auto-Decision Principles

Every finding in `review.md` MUST be tagged with ≥1 principle, e.g., `[Pragmatic, Boil Lakes]`.

| Principle | Definition |
|-----------|-----------|
| **Completeness** | Every required dimension is addressed — no gaps in scope, test, or docs |
| **Boil Lakes** | No over-scope; cut what isn't on the critical path |
| **Pragmatic** | Favor simpler, fewer moving parts over clever abstractions |
| **DRY** | No duplicated logic across components; reuse before rebuild |
| **Explicit** | No hidden defaults; surface all decisions and assumptions |
| **Bias to Action** | When in doubt, prefer the path that advances over the path that waits |

### EXIT PLAN MODE GATE

Script: `scripts/pm/exit-gate-check.sh [--skip-gate]`

**Exit codes:**
- `0` — review.md present with all 4 sections and a closing verdict; proceed to ExitPlanMode.
- `1` — gate failure: missing file, missing sections, or missing closing verdict. Block ExitPlanMode.
- `2` — fatal: cannot resolve branch, or invalid branch name (path-traversal guard per WARN-6).

**Mandatory sections** (detected via `^##+ <Section>\b` — matches `##` through `####` and deeper):
`Architecture`, `Tests`, `Risks`, `Decisions`.

**Branch resolution:** `git rev-parse --abbrev-ref HEAD`; detached HEAD → `sha-<short>`. Branch name must match `^[A-Za-z0-9._/-]+$` and must not contain `..`.

**Audit-line format:**
- Gate failure (sections): `[GATE-FAIL] missing: <section> [<section>...]` → stderr, exit 1.
- Gate failure (verdict): `[GATE-FAIL] missing closing verdict: review.md must END with 'NO UNRESOLVED DECISIONS' or contain a '**UNRESOLVED DECISIONS:**' block` → stderr, exit 1.
- Invalid branch: `[GATE-FAIL] invalid branch name: <name>` → stderr, exit 2.
- Skip: `[GATE-SKIPPED] <branch>` → stderr + 1 line in `.sdd/timeline.jsonl` with `outcome=skipped-gate`.

**`--skip-gate` flag:** Bypasses section check; use only when review.md cannot be written. Costs an audit trail entry (T090 tracks skip ratio via `outcome=skipped-gate`). Calls `timeline-log.sh end --skill=plan-review --outcome=skipped-gate`.

**Canonical test cases:** `scripts/pm/test/exit-gate-check.test.sh` (14 cases: happy, missing-1, missing-2, skip-gate, dotdot-traversal, space-branch, detached-HEAD, nested-headings).

#### Closing Verdict (EXIT GATE, FR-7)

Every `review.md` MUST end with an explicit closing verdict. The gate (`scripts/pm/exit-gate-check.sh`) refuses `ExitPlanMode` (exit 1) if neither form is present.

**Accepted forms (mutually exclusive — either satisfies the gate):**

1. **`NO UNRESOLVED DECISIONS`** — The last non-blank line of `review.md` must be exactly this string (trailing whitespace tolerated). Use when all decisions raised during review are resolved.

2. **`**UNRESOLVED DECISIONS:**` block** — A line matching `^\*\*UNRESOLVED DECISIONS:\*\*` anywhere in `review.md`. Use when open items remain; list each item below the heading.

**Anti-pattern guarded against:** dumping findings and exiting without stating a verdict ("dump and leave"). The gate makes this impossible — a verdict-less report blocks `ExitPlanMode`.

**"Ends with" semantics:** the last *non-blank* line must equal `NO UNRESOLVED DECISIONS`. A trailing newline does not defeat this (uses `awk 'NF{last=$0} END{print last}'`).

### Dual-Voice Review

**Trigger (FR-14):** `changed_files ≥ 3` OR `new_classes ≥ 2`. Changed-files source = same `git merge-base HEAD origin/main` (fallback `HEAD~5..HEAD`) rule as FR-11. New-classes counted via diff grep `^\+(class |export (default )?class )`.

**Dispatch:** single Agent call block (parallel) — subagent A `claude-sonnet-4-6` (engineering voice), subagent B `claude-opus-4-7` (DX voice). Both write findings buffers; orchestrator merges.

**Tag schema:** every finding carries exactly one of `[both]` (intersection), `[eng-only]` (sonnet-unique), `[dx-only]` (opus-unique), or `[partner-failed]` (survivor-tag on partial dispatch failure).

**R-3 auto-fallback (rolling 5-run window):** read last 5 plan-review `end` events with all 3 finding fields from `.sdd/timeline.jsonl`. If `len < 5` → runs 1–4 emit `"warming up (N/5)"` in review.md tail (dual-voice still fires). If `len == 5` and `(unique_eng + unique_dx) / (unique_eng + unique_dx + both) < 0.30` → auto-fallback to single-voice this run + warning `"Dual-voice efficiency: <PCT>% (below 30% threshold)"`.

**Threshold reconciliation vs FR-11:** dual-voice ≥3 fires BEFORE the Phase-0 >8 reduce prompt. The two are independent triggers — both can fire on the same plan (large dual-voice review + REDUCE proposal).

**Cost envelope:** ~3× single-voice on triggered runs (parallel sonnet+opus + merge overhead). Override via `/sdd plan-review --single-voice` (NFR-6) — review.md tail notes `"user-forced single-voice"`.

**Partial-failure rule:** if one subagent returns non-zero AND the other succeeded → tag survivor's findings `[<voice>-only, partner-failed]`; emit telemetry warning; do NOT block the review. Below-threshold path runs sonnet only with tail note `"single-voice mode: below dual-voice threshold"`.

**Telemetry writeback:** end of every plan-review run calls `scripts/pm/timeline-log.sh end --skill=plan-review --outcome=ok --duration_ms=N --findings-unique-eng=$ue --findings-unique-dx=$ud --findings-both=$b` (T001 extension fields, T090 SC-4 source).

### Review Sections (1-6)

**Issue format** (shared across all sections):

```
[SECTION]-[N]: [One-line title]
Problem: [reference specific epic.md sections]
Impact: [what happens if shipped as-is]
Options:
  A) [Recommended] — Effort: [S/M/L], Risk: [L/M/H]
  B) [Alternative] — Effort: [S/M/L], Risk: [L/M/H]
  C) Do nothing — Risk: [consequence]
Recommend A because: [one sentence tied to engineering preference]
Confidence: [1-10] — [basis: code-reading / pattern match / gut feel]
```

**Mode behavior:** FULL = each issue individually, wait for response. QUICK = one most critical issue per section, all at once. REDUCE = focus on what to cut.

#### Section 1: Architecture Review

Evaluate: component boundaries, data flow (input to output trace), state management, coupling justification, integration failure modes, rollback posture. Security smell check if plan touches user data, credentials, external APIs, or file paths. Mandatory: one ASCII architecture diagram (mark new components with a star).

#### Section 2: Failure Mode Analysis

Two tables:

```
TABLE 1 — WHAT CAN FAIL
| Codepath/Script | What can fail | Exception/Error class |

TABLE 2 — HOW IT'S HANDLED
| Exception/Error | Rescued? | Rescue Action | User sees | Test? | Severity |
```

Rules: Catch-all error handling is ALWAYS a smell — name specific exceptions. Rescued=N + Test=N + User sees=Silent = CRITICAL GAP. For each new data flow, trace 4 shadow paths: happy / nil / empty / error.

#### Section 3: Code Quality & DRY Review

DRY violations (reference file:line), module structure, naming conventions, error handling consistency, over/under-engineering, complexity hotspots (>5 files in one task, >200-line scripts).

#### Section 4: Test Strategy Review

```
TEST COVERAGE MAP
| What's new | Happy path test? | Failure path test? | Edge case? | Test type |
```

Key questions: Does plan specify test strategy? Can you describe a 2AM-confidence test for each codepath? What test would a hostile QA engineer write? Test pyramid shape? Flakiness risks?

#### Section 5: Performance & Resource Review

Evaluate (skip irrelevant): file I/O in loops, shell spawning overhead, API batching, context window pressure, parallel safety, scaling characteristics.

#### Section 6: PRD Traceability Audit

```
TRACEABILITY AUDIT
| PRD Req | Epic maps to | Task(s) | Verification | Status |
| FR-X    | AD-X, section | T-X    | [test type]  | mapped/unmapped/skipped |
```

Unmapped MUST reqs = CRITICAL. Check for vague verification, task-requirement misalignment, scenario coverage.

### Verdict Framework

Three levels, determined by review findings:

| Verdict | Condition | Next Step |
|---------|-----------|-----------|
| **READY** | 0 critical gaps + 0 unmapped MUST + 0 unresolved decisions | `epic-start` or `epic-oneshot` |
| **READY WITH WARNINGS** | 0 critical + 0 unmapped but has warnings | Fix warnings or proceed |
| **BLOCKED** | Any critical gap OR unmapped MUST OR blocking decision | Fix issues, then re-review |

### Required Outputs

Generated after all sections regardless of mode:

1. **Existing Code Reuse** — Functionality / Existing code / Reused? / Recommendation
2. **Not in Scope** — Deferred items with reasons (or "No items deferred")
3. **Failure Modes Registry** — Consolidated table with CRITICAL GAPS count and WARNINGS count
4. **Unresolved Decisions** — Issue / Section / Recommended / Risk if unresolved
5. **Completion Summary:**

```
PLAN REVIEW — COMPLETION SUMMARY
Epic:              $EPIC_NAME
Mode:              FULL / QUICK / REDUCE
PRD coverage:      X/Y MUST requirements mapped (Z%)

Arch issues: ___  |  Failure modes: ___ (__ critical)
Quality: ___      |  Test gaps: ___
Perf: ___         |  PRD trace: ___ unmapped

Code reuse: ___   |  Deferred: ___  |  Unresolved: ___
Lake Score: X/Y (Z%) decisions chose complete option

VERDICT:  READY / READY WITH WARNINGS / BLOCKED
Reason:   [one line]
```

### Save Review

Save to `.sdd/epics/$EPIC_NAME/plan-review.md`:

```markdown
---
epic: $EPIC_NAME
prd: [from epic frontmatter]
mode: full|quick|reduce
reviewer: claude
created: [date -u +"%Y-%m-%dT%H:%M:%SZ"]
verdict: ready|ready-with-warnings|blocked
critical_gaps: [N]
warnings: [N]
---

# Plan Review: $EPIC_NAME

[Full review content — all sections, outputs, completion summary]
```

### Post-Review

1. Confirm: `Plan review saved: .sdd/epics/$EPIC_NAME/plan-review.md`
2. Display Completion Summary.
3. Next steps based on verdict.

### Interaction Rules

1. One issue = one interaction (FULL mode). Lead with directive recommendation.
2. Map every recommendation to an engineering preference (DRY, minimal diff, etc.).
3. Reference specifics: epic.md section, file path, PRD requirement ID. No vague feedback.
4. 3-option format for non-trivial issues (A recommended, B alternative, C do nothing).
5. No code writing — this is a REVIEW. Only identify what needs to change.
6. If user says "skip" — note unresolved, proceed.

### Context Pressure Protocol

**Never skip:** Step 0 (Scope Challenge) + Section 6 (PRD Traceability) + Completion Summary.
**Compress:** Section 1 to diagram + top issue. Section 2 to critical gaps only. Section 3 skip if no DRY violations. Section 4 to coverage map only. Section 5 skip unless PRD mentions performance.
**Always generate** plan-review.md file and Completion Summary.

### Model Tier

**FULL/REDUCE:** Requires `opus` — architecture review and failure mode analysis demand strong reasoning.
**QUICK:** Runs on `sonnet` — structured checklist with single-pass analysis.
