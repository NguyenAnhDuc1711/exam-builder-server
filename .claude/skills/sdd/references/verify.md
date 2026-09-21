# Verification Pipeline

Two-phase quality gate for epics. Phase A is a semantic review (LLM analyzes docs against PRD). Phase B is automated integration testing (build, lint, unit, integration + QA). Both must pass before merge.

## epic-verify

Orchestrate the full pipeline: Phase A -> Phase B -> Write State.

### Pre-flight

```bash
EPIC_NAME="{epic}"
test -d .sdd/epics/$EPIC_NAME || { echo "Epic not found"; exit 1; }
mkdir -p .sdd/context/verify/epic-reports 2>/dev/null
```

Read `.sdd/epics/$EPIC_NAME/epic.md` to get PRD reference and task list.

### Phase A: Semantic Review

Assemble input for LLM review:
1. Read epic description, PRD, and all task files from `.sdd/epics/$EPIC_NAME/`
2. Read handoff notes from `.sdd/context/handoffs/`
3. Collect git diff: `git diff main..HEAD --stat`
4. Read previous verify reports from `.sdd/context/verify/epic-reports/` (if any)

#### Review Protocol

Act as a Senior Technical Reviewer. Analyze documentation only — do not run code.

For each MUST requirement in the PRD:

1. **Coverage check:** Does at least one task implement this requirement?
2. **Test coverage:** Does test code exist that validates this requirement?
3. **Acceptance criteria:** Is each AC in the task fully implemented?

Produce a Coverage Matrix:

| PRD Requirement | Task(s) | Implemented | Test Coverage | Status |
|-----------------|---------|-------------|---------------|--------|
| FR-1: ... | T243 | Yes/No | Yes/No | Pass/Gap |

#### 3D Analysis Framework

Evaluate changes across three orthogonal dimensions. Each dimension has specific audit items; a gap in any single dimension is sufficient to flag a finding.

**Dimension 1 — Architecture Integrity**
- Module boundaries respected (no cross-component side effects)
- Dependency direction correct (no circular imports, no upward calls)
- Public API surface changes are intentional and documented
- Shared state mutations are explicitly coordinated
- Config / environment changes propagated to all consumers

**Dimension 2 — Requirement Coverage**
- Every MUST acceptance criteria maps to at least one closed task
- Every SHOULD criteria is either implemented or explicitly deferred
- Implicit requirements addressed (auth, error messages, logging, accessibility)
- Edge cases derived from requirements have test coverage
- No orphan tasks (tasks that implement nothing in the PRD)

**Dimension 3 — Code Quality**
- Error paths handled (not just happy path)
- Resource cleanup present (file handles, connections, temp files)
- No hard-coded secrets, credentials, or environment-specific values
- Naming consistent with project conventions
- Dead code and unused imports removed

#### Gap Report

For each unmet requirement, record:
- Requirement ID and description
- What is missing (implementation, tests, or both)
- Severity: `critical` (blocks release), `high` (major feature gap), `medium` (minor), `low` (cosmetic)
- Recommended fix

Gap categories (check all six):
1. **Integration Gap** — interfaces between modules do not match
2. **Delivery Gap** — code works but user cannot access the feature
3. **Phantom Completion** — task closed but feature not actually working
4. **Missing Requirement** — AC not addressed by any task
5. **Quality Gap** — works but lacks error handling, tests, or docs
6. **Regression Gap** — later task modifies code an earlier task depends on

#### Failure Mode Analysis

For every new or modified codepath, build two tables. This is the most commonly missed part of verification — skip it at your peril.

**TABLE 1 — What Can Fail**

Enumerate each codepath introduced or modified by the epic. For every external call, I/O operation, parse step, or state transition, identify the failure class.

| Codepath | What can fail | Exception / Error class |
|----------|---------------|------------------------|
| `loadConfig()` | File missing, JSON malformed | `FileNotFoundError`, `JSONDecodeError` |
| `POST /api/items` | Network timeout, 4xx/5xx | `TimeoutError`, `HTTPError` |
| `writeReport()` | Disk full, permission denied | `IOError` |

**TABLE 2 — How It's Handled**

For each failure from Table 1, trace whether the code actually handles it.

| Exception | Rescued? | Rescue Action | User sees | Test? | Severity |
|-----------|----------|---------------|-----------|-------|----------|
| `FileNotFoundError` | Yes | Create default config | Warning msg | Yes | Low |
| `TimeoutError` | No | — | Crash / hang | No | Critical |
| `JSONDecodeError` | Yes | Log + abort | Error msg | No | High |

**4 Shadow Paths Heuristic** — for each function, verify behavior on:
1. **Happy path** — normal input, expected output
2. **Nil path** — null / undefined / None inputs
3. **Empty path** — empty string, empty list, zero-length file
4. **Error path** — exception thrown by a dependency

Any shadow path without a test or explicit guard is a finding.

#### Code Review Checklist

For each file in `git diff --name-only main..HEAD`, verify:

- [ ] Function signatures match their callers (no argument mismatch)
- [ ] Return types consistent with what consumers expect
- [ ] Error conditions produce actionable messages (not bare `raise` or `exit 1`)
- [ ] Side effects documented or obvious from naming
- [ ] No TODO/FIXME/HACK left without a tracking issue
- [ ] Config keys used in code exist in default config
- [ ] New dependencies added to the correct manifest (package.json, Cargo.toml, etc.)

#### Scope Drift Detection

Compare each task's declared `files:` frontmatter against actual changes:

```bash
git diff --name-only main..HEAD
```

- Extra files outside declared scope in a different component -> **major drift**
- Extra files in same directory as declared files -> **minor drift**
- Declared files not touched -> **requirements missing** (check if AC requires them)
- Shared config files (package.json, root configs) -> do not flag as drift

#### Fix-First Heuristic

Classify each finding before presenting:

| Category | Examples | Action |
|----------|----------|--------|
| AUTO-FIX | Formatting, trailing whitespace, unused imports, typos | Apply silently, log result |
| ASK | Architecture changes, logic mods, API changes, dependency additions | Present to user with options |

For ASK findings, offer:
- A) Apply suggested fix
- B) Skip — accept as-is
- C) Flag as technical debt

#### Phase A Report

Write to `.sdd/context/verify/epic-reports/{epic}-{YYYYMMDD-HHMMSS}.md`:

```yaml
---
epic: {epic}
phase: A
generated: {ISO datetime}
assessment: EPIC_READY | EPIC_GAPS | EPIC_NOT_READY
quality_score: {X}/5
total_issues: {N}
closed_issues: {X}
open_issues: {Y}
---
```

Report must include all six analyses: Coverage Matrix, Gap Report (with Failure Mode tables), Integration Risk Map, Quality Scorecard, Recommendations, Phase B Preparation.

Assessment criteria:
- **EPIC_READY**: All MUST requirements covered, no critical/high gaps
- **EPIC_GAPS**: Some gaps exist but none critical — can proceed with acceptance
- **EPIC_NOT_READY**: Critical gaps or missing core functionality

#### ENFORCEMENT: Phase A Gate

> **STOP.** If gaps are found, present the gap report to the user. Do NOT proceed to Phase B until the user explicitly chooses an option.

Developer options:
1. **Proceed to Phase B** — no critical gaps, continue to tests
2. **Fix gaps first** — address critical/high gaps, then re-run verify
3. **Accept gaps** — acknowledge as technical debt, proceed to Phase B
4. **Abort** — stop verification, resume development

Wait for explicit user choice. Do NOT auto-proceed.

### Phase B: Integration Testing

**Prerequisite:** Phase A must have run. If assessment is `EPIC_NOT_READY`, refuse to proceed.

```bash
REPORT=$(ls -t .sdd/context/verify/epic-reports/${EPIC_NAME}-*.md 2>/dev/null | grep -v "final" | head -1)
test -n "$REPORT" || { echo "No Phase A report. Run epic-verify Phase A first."; exit 1; }
```

Read the Phase A report. Extract the "Phase B Preparation" section — it contains test scenarios, integration points, and a smoke test checklist that drive what to test.

#### Test Coverage Map

Before running tests, build a coverage map from the Phase A report and code diff. This ensures no new functionality goes untested.

| What's new / changed | Happy path test? | Failure path test? | Edge case? | Test type |
|----------------------|------------------|--------------------|------------|-----------|
| `loadConfig()` | Yes | Yes (missing file) | Empty file | Unit |
| `POST /api/items` | Yes | No | No | Integration |
| CLI `--format` flag | Yes | No | Invalid value | E2E |

Every row with "No" in a test column is a gap. Write tests to fill gaps before proceeding to the tier runner.

#### 4-Tier Test Runner

Execute tiers sequentially. Each tier must pass before the next runs.

**Tier 1 — Build:** Compile or bundle the project. Catches syntax errors, missing imports, type mismatches.
```bash
# Detect project type and run: npm run build / cargo build / go build ./...
# Exit 0 = PASS, non-zero = FAIL
```

**Tier 2 — Lint:** Static analysis. Catches style violations, unused variables, potential bugs.
```bash
# Run: npm run lint / cargo clippy / golangci-lint run
```

**Tier 3 — Unit Tests:** Isolated function-level tests. Fast, no external dependencies.
```bash
# Run: npm test / cargo test / go test ./...
```

**Tier 4 — Integration + E2E:** Tests that exercise real interactions between modules, external APIs, or user flows.
```bash
# Run: npm run test:e2e / tests in tests/e2e/epic_{name}/
```

If no tests exist for the epic, write smoke + integration tests based on Phase A report findings before running. Use the Test Coverage Map to prioritize what to write.

#### Coverage Thresholds

After Tier 3+4, evaluate coverage:
- **Minimum**: every MUST requirement has at least one test (happy path)
- **Target**: every MUST requirement has happy + failure path tests
- **Stretch**: edge cases covered for critical codepaths

If minimum threshold is not met, flag as a Phase B gap before proceeding.

#### ENFORCEMENT: Tier Failure Gate

> **STOP.** If any tier fails, report the failure tier and specific errors. Do NOT continue to subsequent tiers. Present the user with:
> - Which tier failed
> - Exact error output
> - Suggestion to fix and re-run

#### Fix Loop

When tests fail:
1. Analyze failure output
2. Apply targeted fix
3. Re-run the failing tier
4. Repeat until pass, max iterations reached (default: 30), or **no-progress stall** trigger fires (FR-2 stop-loss).

Track iteration state in `.sdd/context/verify/epic-state.json`.

##### No-Progress Stop-Loss (FR-2 / AD-4)

Per iteration, compute the stall-detection 3-tuple:
- `failing_count` — integer count of failing tests in current run.
- `error_pattern_hash` — `sha1(test_name + "|" + first_non_blank_line(error_msg))`
  where `first_non_blank_line` skips leading whitespace-only lines and returns the
  first non-empty stack/assertion line.
- `tier_name` — `unit | integration | e2e | …` derived from test path or `--tier` flag.

Maintain a **ring buffer of size 3** (last 3 iterations' tuples). After each iteration:
- Append current tuple to ring buffer.
- If buffer contains 3 entries AND all 3 are element-wise identical:
  - Emit stderr (AD-7 grammar):
    `verify: fr2-no-progress-stall: 3 identical iterations on tier=<T> — exiting non-zero`
  - Exit non-zero with reason `no-progress-stall`.
- If any element of the current tuple differs from the previous: the 3-identical check
  next iter will be false until 3 new identical tuples accumulate (buffer reset implicitly).

CLI flag: `--max-iter=N`
- Overrides default cap of 30 iterations for known-slow tiers.
- Stop-loss 3-tuple check still applies — flag only changes the upper iter cap.
- Example: `verify-run --tier=e2e --max-iter=60` for slow integration suites.

**R-2 mitigation (false-positive prevention):** hash + tier disambiguators ensure flaky
slow tests with shifting error messages do NOT trigger stall — only consistently-identical
3-tuples do.

**NFR-1 carve-out:** Happy path (suite passes on iter 1) emits empty stderr; the
`fr2-no-progress-stall` line ONLY fires on stall trigger.

#### QA Tier

After all 4 tiers pass, run QA scenarios if available.

> **Load `qa.md` reference** for QA scenario creation and execution. Do not duplicate QA instructions here.

QA results are appended to the verify report but are **non-blocking** — QA failures do not prevent merge. They are informational.

### Verify State

After both phases complete, write results to `.sdd/context/verify/epic-state.json`:

```json
{
  "phase_a": "PASS",
  "phase_b": "PASS",
  "overall": "PASS",
  "timestamp": "2026-01-01T00:00:00Z",
  "epic": "{epic}",
  "iterations": 1
}
```

Rules:
- `phase_a`: `PASS` if assessment is EPIC_READY or EPIC_GAPS (accepted). `FAIL` if EPIC_NOT_READY.
- `phase_b`: `PASS` if all 4 tiers pass. `FAIL` if any tier fails after max iterations.
- `overall`: `PASS` only if both phase_a AND phase_b are `PASS`.

### Final Report

Write to `.sdd/context/verify/epic-reports/{epic}-final-{timestamp}.md`:

```yaml
---
epic: {epic}
phase: final
generated: {ISO datetime}
phase_a_assessment: {EPIC_READY|EPIC_GAPS|EPIC_NOT_READY}
phase_b_result: {PASS|FAIL|PARTIAL}
final_decision: {EPIC_COMPLETE|EPIC_PARTIAL|EPIC_BLOCKED}
quality_score: {X}/5
total_iterations: {N}
---
```

Decision matrix:

| Phase A | Phase B | Decision |
|---------|---------|----------|
| READY | PASS | EPIC_COMPLETE |
| GAPS (accepted) | PASS | EPIC_COMPLETE |
| READY | PARTIAL | EPIC_PARTIAL |
| GAPS | PARTIAL | EPIC_PARTIAL |
| Any | FAIL | EPIC_BLOCKED |
| NOT_READY | N/A | Phase B should not have run |

#### Report Sections

The final report must include all of the following:

1. **Metadata table** — epic name, Phase A/B statuses, decision, quality score, iteration count, generated timestamp
2. **Coverage Matrix (final)** — copy from Phase A, update statuses for gaps fixed during Phase B
3. **Gaps Summary** — three subsections:
   - *Fixed in Phase B*: gaps resolved during fix iterations
   - *Accepted (technical debt)*: gaps the developer explicitly accepted
   - *Unresolved*: remaining gaps not fixed and not accepted
4. **Failure Mode Summary** — condensed version of Table 1 + Table 2 from Phase A, updated with any fixes applied
5. **Test Results (4 tiers)** — pass/fail counts per tier from the last Phase B run
6. **Phase B Iteration Log** — table of `Iter | Result | Issues Fixed | Duration` from `epic-state.json`
7. **Files Modified** — list from `git log` during Phase B

#### Gap Classification for Final Decision

When gaps remain at report time, classify each to decide accept vs fix:

| Gap Severity | User-Facing? | Has Workaround? | Decision |
|--------------|-------------|-----------------|----------|
| Critical | Yes | No | Must fix — EPIC_BLOCKED |
| Critical | Yes | Yes | Fix or accept with documented workaround |
| High | Yes | No | Fix before merge |
| High | No | N/A | Accept as tech debt, create follow-up issue |
| Medium | Any | Any | Accept, log in report |
| Low | Any | Any | Accept silently |

For each accepted gap, the report must include: gap ID, reason for acceptance, follow-up issue number (if created).

### Post-Closure

Only execute if `final_decision` is `EPIC_COMPLETE`:

1. **Git tag:** `git tag "epic-${EPIC_NAME}-verified"`
2. **Archive context:** move `.sdd/context/epics/${EPIC_NAME}.md` to `.sdd/context/epics/.archive/`
3. **Commit report:** `git add .sdd/context/verify/ && git commit -m "[Epic-Complete] ${EPIC_NAME}"`
4. **Clear verify state:** reset `.sdd/context/verify/epic-state.json`

If `EPIC_PARTIAL`: present options (ship as-is, continue fixing, create follow-up epic).
If `EPIC_BLOCKED`: suggest reviewing failures and re-running.

### Skillbook Extraction

After Phase A + Phase B complete, check for systemic patterns worth capturing:

**Trigger:** If >=2 tasks failed or had gaps for the same root cause (e.g., missing import convention, wrong config pattern, repeated test setup issue), extract a skillbook entry.

**Process:**
1. Review the Gap Report and Phase B iteration log for repeated failure patterns
2. If a systemic pattern is found, append to `.sdd/context/skillbook.md`:

→ See context.md §Skillbook YAML Template

3. If no systemic pattern found, skip silently

This extraction is non-blocking — verification results are not affected.

### Next Steps

- **EPIC_COMPLETE** -> `epic-merge {epic}`
- **EPIC_PARTIAL** -> Developer decides
- **EPIC_BLOCKED** -> Fix issues, re-run `epic-verify {epic}`

## Gap Management

### accept-gaps

Accept specific gaps as known technical debt:

1. Read the latest Phase A report
2. Mark specified gap IDs as accepted
3. Update the report with acceptance notes
4. Phase A gate allows proceeding to Phase B

### fix-gap

Apply a targeted fix for a specific gap:

1. Read gap details from the Phase A report
2. Implement the fix (code change or test addition)
3. Commit: `Issue #{N}: Fix gap — {description}`
4. Re-run Phase A to verify the fix resolved the gap

## Verify Lifecycle Commands

Operations for managing in-progress and past verification runs. All state is stored in `.sdd/context/verify/epic-state.json`.

### verify-abort

Abort an active verification and deactivate the fix loop.

1. Read `.sdd/context/verify/epic-state.json` — confirm `active_epic` is set and matches the target epic
2. Prompt developer for abort reason (logged for audit)
3. Write state: set `active_epic` to null, record `last_abort` with epic name, timestamp, reason, and iteration count at abort
4. The Ralph hook deactivates when `active_epic` is null — no further enforcement

Resume later with `verify-resume` or start fresh with `epic-verify`.

### verify-resume

Resume a previously aborted or crashed verification from its last checkpoint.

Three entry states:
- **`active_epic` set, matches target** — session crashed; state is intact, re-run Phase B from current iteration
- **`active_epic` null, `last_abort` matches target** — explicitly aborted; re-initialize state from abort record, restore iteration counter, then run Phase B
- **Neither** — no state to resume; direct the developer to `epic-verify` instead

On resume, skip steps already completed (test writing, state init). Run `epic-verify.sh` from the restored iteration. The Ralph hook reactivates automatically.

### verify-status

Display current verification state without modifying anything.

Shows: epic name, current phase (A/B/Complete), iteration N/max, verify mode (STRICT/RELAXED), Ralph hook status (active/inactive), timestamp of last iteration, and compact iteration history if any.

If no active verification, show the latest report path and suggest `verify-history` or `epic-verify`.

### verify-history

List all past verification reports for an epic, sorted newest-first.

```bash
ls -t .sdd/context/verify/epic-reports/${EPIC_NAME}-*.md
```

For each report, extract from frontmatter: date, phase (A or final), assessment/decision, quality score, iteration count. Display as a table.

Also check for an active verification and show its status inline if present.
