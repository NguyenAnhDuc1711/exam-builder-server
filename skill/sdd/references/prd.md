# PRD Authoring

Write, validate, and refine Product Requirement Documents. Commands: `prd-new`, `prd-validate`, `prd-qualify`, `prd-edit`.

See [conventions.md](conventions.md) for shared rules (frontmatter, paths, git, GitHub ops).

---

## prd-new

3-wave guided discovery to write a Product Requirement Document.

### Preflight

1. Validate feature name: non-empty kebab-case (`^[a-z0-9][a-z0-9-]*[a-z0-9]$`).
2. If `.sdd/prds/{feature}.md` exists, ask: overwrite?
3. If `.sdd/prds/.draft-{feature}.md` exists, ask: resume draft?
4. `mkdir -p .sdd/prds 2>/dev/null`

### Role

Senior PM with deep technical understanding. Apply four lenses: Skeptic (what could go wrong?), User (real pain?), Engineer (buildable?), PM (MVP scope?).

### 3-Wave Guided Discovery

**Adaptive entry (FR-4 / 50-point scoring rubric):**

Score the input against four content elements (50 points total). Each element earns its full
point value ONLY if the heading is present AND the body contains ≥1 non-blank, non-placeholder
line. Heading-grep alone is insufficient (R-4 mitigation: prevents vague heading-only PRDs
from silently routing to light path).

| Element            | Points | Validation                                                      |
|--------------------|--------|-----------------------------------------------------------------|
| Problem statement  | 10     | Heading present + body has ≥1 non-blank, non-placeholder line   |
| Target user        | 10     | Heading present + body has ≥1 non-blank, non-placeholder line   |
| Success metric     | 15     | Heading present + body has ≥1 non-blank, non-placeholder line   |
| Scope (IN/OUT)     | 15     | Heading present + body has ≥1 non-blank, non-placeholder line   |

Placeholders that score 0 (case-insensitive): `[TBD]`, `TBD`, `TODO`, `FIXME`, `[XXX]`,
empty body, whitespace-only body.

**Routing decision:**
- Score > 40: route = light (direct PRD generation; equivalent to `--yolo` path).
- Score ≤ 40: route = discovery (start Wave 1 / Express Path).
- Score == 40 (boundary): word-count tiebreaker — ≥200 words → light; <200 → discovery.

**Audit emission (AD-7 grammar, every invocation):**
`prd-new: fr4-adaptive-entry: score=X/50 → route=<light|discovery>`

NOTE: This routing audit line fires on every prd-new invocation by design (it IS the
routing-decision audit, not an edge-case fault line). NFR-1 byte-identity for prd-new
means "same route for same input", not "empty stderr". This reconciles with the AD-7
happy-path carve-out for the other 4 fixes.

**2-layer defence (R-4 mitigation):** This rubric is a ROUTER only. Semantic quality of
PRD body content is enforced by the existing `prd-validate` second-layer semantic gate.
Rubric + prd-validate = 2-layer defence (intentional).

**Determinism contract (SC-4):** Same input → same route over 10 consecutive runs. No
non-deterministic inputs (date, random, env state) influence scoring.

**Wave 1 — Problem Space:**
- What specific problem? Concrete scenario of the pain?
- Who experiences it? Frequency? Severity (annoying vs blocking)?
- What happens today without this? Existing workarounds?
- Why solve NOW? What triggered this?

Ask, then STOP. Save checkpoint to `.sdd/prds/.draft-{feature}.md` after user responds.

**Wave 2 — Solution & Users:**
- Specific solution in mind, or just the problem?
- Minimum viable vs dream version?
- Distinct user types? (solo dev vs team lead vs CI bot)
- Examples from other tools?
- What should this NOT do?

Ask, then STOP. Update checkpoint after response.

**Wave 3 — Constraints & Risks:**
- Technical constraints? (existing systems, backward compat, performance)
- Timeline/resource constraints?
- Biggest risk? What could make this fail?
- Dependencies on other features or external systems?

Ask, then STOP. Update checkpoint, check completion gate.

**Express Path** (for detailed upfront input): Parse input, summarize understanding (Problem/Users/Solution/Risk), ask "what's missing?", fill gaps with 1-3 targeted questions.

**Completion gate — ALL must be true:**
1. Can explain the problem in one sentence
2. Know the primary user persona(s)
3. Understand what "done" looks like
4. Know the biggest risk
5. Know what's out of scope

### Synthesis

Present structured blueprint before writing:

```
Blueprint for '{feature}':
- Problem (1 sentence): [...]
- Primary users: [persona 1], [persona 2]
- Solution approach: [1-2 sentences]
- Scale: Small / Medium / Large
- Key risk: [...]
- Out of scope: [...]
- Requirement estimate: ~X FR, ~Y NFR
```

Ask: "Proceed with this blueprint?" Only write after confirmation.

**Scale heuristics:** SMALL: bug fix, ≤3 reqs. MEDIUM: 3-8 reqs (default). LARGE: 8+ reqs, migration, multi-component.

### PRD Structure

Save to `.sdd/prds/{feature}.md` with sections:
- **Frontmatter:** name, description, status (`backlog`), priority, scale, created, updated
- **Executive Summary:** what, who, why, why now (3-5 sentences)
- **Problem Statement:** from USER perspective — who, frequency, severity, workarounds
- **Target Users:** 2-4 personas with name/role, context, primary need, pain level
- **User Stories:** `US-N` format with persona reference + testable acceptance criteria
- **Requirements:** `FR-N` (MUST), `NTH-N` (nice-to-have), `NFR-N` (non-functional). Each with GIVEN/WHEN/THEN scenarios.
- **Success Criteria:** measurable with thresholds and measurement method
- **Risks & Mitigations:** severity/likelihood table (1 for SMALL, 3+ for MEDIUM, 5+ for LARGE)
- **Constraints & Assumptions:** hard limits + "if wrong, then [consequence]"
- **Out of Scope:** explicit list with rationale
- **Dependencies:** format `[Dep] — [Owner] — [Status]`
- **_Metadata:** requirement_ids, scale, discovery_mode, validation_status

### Quality Checks

Before saving, verify:
- **Structural:** All required sections present per scale (SMALL: core sections; MEDIUM: + personas, user stories; LARGE: + full dependency map, migration plan)
- **Executive Summary:** Answers what, who, why, why-now in 3-5 sentences
- **Requirements:** All use ID format (`FR-N`, `NTH-N`, `NFR-N`), sequential, unique. Each has at least one GIVEN/WHEN/THEN scenario.
- **Personas:** Every user story references a defined persona; no orphan personas
- **Success Criteria:** Every criterion has a measurable threshold AND measurement method
- **Risks:** Each has severity + likelihood + mitigation. Count meets scale minimum (1 SMALL, 3+ MEDIUM, 5+ LARGE)
- **Metadata:** `_Metadata.requirement_ids` matches actual IDs in document; `scale` matches content depth
- **Coherence:** No contradictions between Out of Scope and Requirements; dependencies have owner + status

Post-creation: delete draft, confirm, show summary and next steps.

### Model Tier

Requires `opus` — nuanced discovery, strong PM judgment, quality PRD output.

---

## prd-validate

Validate a PRD for completeness, correctness, and coherence before parsing to epic.

### Preflight

1. Validate feature name (kebab-case).
2. `.sdd/prds/{feature}.md` must exist.

### Role

Critical reviewer — NOT the author. Job is to find gaps, ambiguities, and weaknesses. Apply the Skeptic lens aggressively.

**Rule:** Must find at least 1 issue (warning or critical). Zero findings on first pass indicates shallow review — re-run more carefully.

### Context Loading

Read if they exist (skip silently if missing):
- `.sdd/prds/{feature}.md` — the PRD to validate
- `.sdd/context/tech-context.md` — constraint validation
- `.sdd/context/product-context.md` — persona validation

### Scale Determination

Read `scale` from PRD frontmatter or `_Metadata`. If missing, infer from requirement count and content depth. Scale governs which sections are required and minimum thresholds.

### 3D Validation Framework

**Dimension 1 — Completeness** (are all required parts present?):
- All required sections present and non-empty (per scale)
- Frontmatter complete: name, status, priority, scale, created
- Requirement IDs sequential and unique (`FR-1`, `FR-2`..., `NTH-1`..., `NFR-1`...)
- Every FR/NTH has at least 1 GIVEN/WHEN/THEN scenario
- Every User Story maps to a defined persona (MEDIUM/LARGE)
- No orphan personas (defined but never referenced in stories)

**Dimension 2 — Correctness** (is content internally consistent?):
- Executive Summary answers: what, who, why, why now
- Problem Statement is from USER perspective, not system perspective
- Success Criteria all have measurable thresholds + measurement method
- Risks have severity + likelihood + mitigation
- MUST requirements align with Success Criteria (no gaps)
- Risks align with Assumptions (no contradictions)
- Scale matches actual content depth

**Dimension 3 — Coherence** (is it ready for downstream consumption?):
- Requirements specific enough for prd-parse to create tasks
- Scenarios specific enough to write automated tests from
- No ambiguous terms without definition ("fast", "easy", "scalable")
- Dependencies have owner + status
- No contradictions between sections (Out of Scope items must not appear in Requirements)

### Validation Report

Save to `.sdd/prds/.validation-{feature}.md`:

```
---
prd: {feature}
date: {UTC timestamp}
status: passed/warning/failed
score: X/Y checks passed
---

# Validation Report: {feature}

## Summary
Status: PASSED / WARNING / FAILED
Score: X/Y (completeness: A/B, correctness: C/D, coherence: E/F)
Scale: {detected scale}

## Critical Issues (must fix before prd-parse)
- [ ] [Dimension]: [Issue] — Section: [section] — Fix: [suggestion]

## Warnings (should fix)
- [ ] [Dimension]: [Issue] — Section: [section] — Fix: [suggestion]

## Passed Checks
- [x] [Check name]

## Recommendations
[Actionable improvements beyond pass/fail]
```

### PRD Metadata Update

If PRD has `_Metadata` section, update `validation_status` (passed/warning/failed) and `last_validated` (current datetime).

### Status Thresholds

- **PASSED:** 0 critical issues, 0-2 warnings
- **WARNING:** 0 critical issues, 3+ warnings
- **FAILED:** 1+ critical issues

### Model Tier

Runs on `sonnet` — structured checklist validation, no creative work.

---

## prd-qualify

Orchestrate the prd-validate / prd-edit loop to bring a PRD to validated quality. Runs up to 5 iterations.

### Purpose

Automated quality gate: validate PRD, fix findings, re-validate — repeat until the PRD passes or max iterations reached. The orchestrator manages the loop; agents execute each validate/edit step.

### Loop Flow

```
Record PRD hash
  |
  v
validate -> findings? --no--> PASS (break)
  |
  yes
  |
  v
edit (fix ALL findings in single pass)
  |
  v
Hash changed? --no--> Warn user (re-run / skip menu)
  |
  yes
  |
  v
Next iteration (up to 5)
```

### Pre-Loop Setup

Record loop start time (UTC) and PRD file hash before first iteration for staleness and change detection.

### Iteration Logic

For each iteration (1 to max 5):

1. **Validate** — run prd-validate agent for current PRD state.
2. **Report freshness check** — compare validation report `date:` against loop start time. If report predates loop start, treat as stale (failed iteration).
3. **Suspicious first-pass detection** — if iteration 1 AND report shows `status: passed` with 0 critical issues AND 0 warnings: log warning ("0 findings on first validation — re-running") and trigger one additional validate pass. Accept re-run result regardless.
4. **Pass check** — if validation passes, break loop (skip edit entirely).
5. **Edit** — run prd-edit agent with the full validation findings. Agent must fix ALL issues in a single pass.
6. **Hash comparison** — compute PRD hash after edit. If hash unchanged (edit didn't apply), show user menu:
   - Re-run prd-edit
   - Skip and proceed

   Update stored hash for next iteration.
7. **Increment** and continue.

### Loop Termination

- **Pass:** Validation report has `status: passed` — loop exits normally.
- **Max iterations:** After 5 iterations without pass — warn user, exit loop.
- **User abort:** User chooses to skip from the unchanged-hash menu.

### Post-Loop Verification

After loop exits, verify final state:
- If validation report missing — enter failure menu.
- If `status:` is not `passed` — warn and offer: proceed anyway / re-run.
- If all checks pass — mark prd-qualify complete and advance.

### Model Tier

Requires `opus` — orchestrates validate/edit agents, judges quality gate.

---

## prd-edit

Edit an existing PRD with context awareness and impact analysis.

### Preflight

1. Validate feature name (kebab-case).
2. `.sdd/prds/{feature}.md` must exist.

### Role

Same PM as prd-new but in revision mode. Focus on: consistency after edits, downstream impact, scope control.

### Edit Modes

**Validation-driven** (when `.sdd/prds/.validation-{feature}.md` exists with issues): Present issues, fix ALL in a single pass. This is the mode used by prd-qualify loop.

**Interactive** (default): Show section overview with status indicators, let user select sections to edit.

**Surgical** (when user specifies intent in args): Apply targeted change directly, show diff.

### Post-Edit Checks

- Re-check edited sections against quality standards
- **Impact analysis:** Compare requirement IDs before/after — report added, removed, modified IDs
- If downstream epic exists AND requirements changed, warn about potential epic staleness
- Update `updated` timestamp (preserve `created`)
- Update `_Metadata`: recalculate `requirement_ids`, set `validation_status: pending`

### Hash Tracking

Record PRD file hash before and after edits. If hash unchanged after validation-driven edit, the caller (prd-qualify) uses this to detect failed applies.

### Model Tier

Runs on `sonnet` — structured editing with quality checks. `opus` when validation-driven with complex findings.

---

## Workflow

After PRD is ready, proceed to [doc.md](doc.md) for the conversion pipeline (prd-parse through epic setup).
