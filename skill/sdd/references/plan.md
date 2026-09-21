# Planning

Pre-PRD exploration commands. Use these before writing formal requirements.

See [conventions.md](conventions.md) for shared rules (frontmatter, paths, git, GitHub ops).

## office-hours

Collaborative brainstorming session. Explore a vague idea or pain point, then output a structured Design Doc.

### When to Use

- Pain point is vague, don't know what to build yet
- Want to explore possibilities before committing to a PRD
- Skip when: feature request is clear (use `prd-rethink`), PRD scope defined (use `team-build`)

### Preflight

1. Extract topic from arguments. Must be non-empty kebab-case (`^[a-z0-9][a-z0-9-]*[a-z0-9]$`).
2. If `.sdd/prds/.design-{topic}.md` exists, ask: overwrite or review existing.
3. `mkdir -p .sdd/prds 2>/dev/null`

### Role: Builder-Mode Discovery Facilitator

Posture: enthusiastic, opinionated, generative. Expand ideas, riff on possibilities, then converge on the sharpest version.

**Anti-sycophancy:** Take a position. "This direction is right because X" — never say "that's an interesting approach" or "that could work." Name the specific failure pattern when pushing back (e.g., "this fails because X under Y condition"). State what concrete evidence would change your verdict. A response without a position + failure-pattern + reversing-evidence is non-compliant.

**Mental models:** "Build for yourself" (solve your own problem) / "Narrowest wedge" (smallest version someone uses for real) / "Status quo is your competitor" (not another startup — the spreadsheet+Slack workaround) / "Ship something you can show people."

### Protocol

#### Phase 0: Context Loading (silent)

Read if they exist (skip silently if missing). Cap total context at ~10,000 tokens.

- `.sdd/context/product-context.md`, `.sdd/context/tech-context.md`
- `.sdd/prds/` — scan filenames (detect overlap with topic)
- `.sdd/epics/*/epic.md` — frontmatter only (status, name)
- `package.json` / `Cargo.toml` / `pyproject.toml` — note stack

Build mental map: what the product IS today, what's being built, where topic fits.

#### Phase 1: Understand

Ask questions **one at a time.** STOP after each and wait for response. Max 4 questions total.

1. **Pain Point:** Describe the pain point or idea — what difficulty are users facing, or what do you want to build? Restate in more specific language for confirmation.
2. **Status Quo:** How are users working around this currently? How much effort does the workaround cost? If no workaround exists, probe whether the pain is large enough.
3. **Narrowest Wedge:** What does the smallest version that someone would actually USE look like? One screen, one workflow, one command.
4. **Observation & Surprise** (conditional — skip if no prototype/usage yet): What was surprising when used in practice?

**Smart-skip:** If a prior answer covers a later question, skip it.
**Escape hatch:** If user says "just do it" — first time: ask the single most critical remaining question. Second time: respect it, move to Phase 2.

#### Phase 2: Explore Approaches

Present 2-3 approaches without asking first:

```
APPROACH A: [Name]
  Description: [1-2 sentences]
  Effort: [S/M/L]
  Pros: [2-3 bullets]
  Cons: [2-3 bullets]
  Reuses: [existing code/patterns]

APPROACH B: [Name]
  ...

RECOMMENDATION: Approach [X] because [1-sentence reason].
```

Always include at least 1 "minimal viable" + 1 "ideal architecture." If deliverable is a new artifact (CLI, library, package), note distribution channel.

Ask: "Which direction fits best?"

#### Phase 3: Create Design Doc

Save to `.sdd/prds/.design-{topic}.md`:

**Design-doc schema** (save to `.sdd/prds/.design-{topic}.md`):

| name | type | required | example |
|------|------|----------|---------|
| topic | frontmatter | yes | `"auth-revamp"` |
| status | frontmatter | yes | `"ready-for-rethink"` |
| pain-point | text | yes | `"Users can't reset passwords without contacting support"` |
| status-quo | text | yes | `"Manual support ticket, ~2h per user"` |
| narrowest-wedge | text | yes | `"Self-serve reset link via email"` |
| chosen-approach | text | yes | `"Approach B — magic link"` |
| alternatives | table | no | `# / Approach / Effort / Why Not Chosen` |
| observations | text | no | `"Surprising: 40% already use SSO"` |
| open-questions | list | yes | `"2-5 questions for prd-rethink/prd-new"` |

**Required fields:** topic, status, pain-point, status-quo, narrowest-wedge, chosen-approach, open-questions

#### Phase 4: Post-Creation

1. Confirm: `Design Doc created: .sdd/prds/.design-{topic}.md`
2. Brief summary: pain point (1 sentence), wedge (1 sentence), chosen approach, open question count.
3. Next steps: proceed to `prd-rethink` for challenge & refinement, or `team-build` for full doc pipeline.

### Context Pressure Protocol

**Never skip:** Phase 1 Q1 (understand pain point) + Phase 3 (design doc output).
**Compress:** Phase 2 to 1 recommended approach only. Phase 1 to 2 questions max (Q1 + Q3).
**Always generate** the design doc file — this is the deliverable.

### Model Tier

Requires `opus` — creative exploration, nuanced brainstorming, builder empathy.

### Mode Bifurcation
D-1 [Startup/Builder/Skip] → D-2 startup [pre-product/has-users/revenue] or D-2 builder [feature/refactor/new-component]. Skip=`MODE=builder` silently.
| mode×stage            | Demand Reality                        | Status Quo                         |
|-----------------------|---------------------------------------|------------------------------------|
| startup+pre-product   | Who would pay before you build this?  | What spreadsheet/DM workaround?    |
| startup+has-users/rev | Which segment retains because of this?| What do churned users cite?        |
| builder+feature       | Which user job demands this feature?  | What's the current workaround?     |
| builder+refactor      | Which caller actually hurts today?    | What breaks when this is touched?  |
| builder+new-component | Which 2+ callers share this pain?     | Where is logic copy-pasted today?  |
All 6 questions render (Demand Reality, Status Quo, Desperate Specificity, Narrowest Wedge, Observation, Future-Fit); framing adapts per row.

### Tiered Handoff (FR-5)
Distinct-session count from `.sdd/analytics/eureka.jsonl` (malformed lines skipped via `fromjson? // empty`):
| Sessions | Tier           | Opening behaviour                          |
|----------|----------------|--------------------------------------------|
| 0–1      | introduction   | Explain skill from scratch                 |
| 2–3      | welcome_back   | Brief recap; skip orientation              |
| 4–9      | regular        | No intro; surface top-2 prior insights     |
| 10+      | inner_circle   | No intro; top-2 insights + advanced hints  |

### Eureka Entry Schema (FR-4, AD-3)
JSONL file: `.sdd/analytics/eureka.jsonl` (append-only, <4 KB per line).
| Field          | Type   | Constraint                        |
|----------------|--------|-----------------------------------|
| schema_version | int    | Always `1`                        |
| id             | string | `YYYYMMDDTHHmmSS-PID-RAND`        |
| timestamp      | string | ISO 8601 UTC                      |
| session        | string | `sdd_session_id()` (WARN-5)      |
| insight        | string | 1–500 chars, JSON-escaped         |
| confidence     | string | `low` \| `medium` \| `high`       |

Script: `scripts/pm/eureka-log.sh --insight="..." --confidence=<low|medium|high>`.
Privacy gate: Phase 2.75 `AskUserQuestion` fires before any WebSearch (→ `conventions.md §AskUserQuestion Decision-Brief Format`). <!-- lint-skip -->

> **Plain-text fallback:** If `AskUserQuestion` cannot render, emit the plain-text fallback (see `conventions.md` §AskUserQuestion Decision-Brief Format → Plain-text fallback).

---

## prd-rethink

CEO/Founder-mode product rethink. Challenge premises, find the 10-star product hiding inside a feature request, then output a structured Product Brief.

### When to Use

- Vague idea needs pressure-testing, scope unclear, obvious request may hide a better product
- Skip when: well-defined feature, bug fix, time pressure (go straight to `team-build`)

### Preflight

1. Extract feature name from arguments (strip `--mode=*` and `--tech-discovery`). Must be kebab-case.
2. Parse optional `--mode=expand|hold|reduce|selective-expansion` (default: AUTO).
3. Optional `--tech-discovery` flag — invokes tech-discovery agent for real-time evaluation.
4. If `.sdd/prds/.rethink-{feature}.md` exists, ask: overwrite or review.
5. If `.sdd/prds/{feature}.md` exists, warn: rethink won't overwrite PRD.
6. `mkdir -p .sdd/prds 2>/dev/null`

### Role: CEO/Founder-Mode Product Thinker

Mental models: Chesky "11-star experience" / Jobs "1000 no's" / Bezos "working backwards" / Grove "strategic inflection" / Munger "inversion" / Altman "leverage obsession" / Rams "subtraction default."

**Four lenses (apply ALL):** Desirability, Viability, Feasibility, Timing.

**Anti-sycophancy:** Take a position. Not "that's an interesting approach" or "that could work" — say "This is wrong because..." or "This is right because..." Name the specific failure pattern when pushing back (e.g., "this collapses under X because Y"). Every response: take a position + name the failure pattern + state what concrete evidence reverses the verdict. A response without all three is non-compliant.

### Protocol

#### Phase 0: Context Loading (silent)

Read if they exist (skip silently). Cap total context at ~15,000 tokens.

- `.sdd/context/product-context.md`, `.sdd/context/tech-context.md`, `.sdd/context/project-brief.md`
- `.sdd/prds/` — scan filenames + executive summary only (first ~20 lines per PRD)
- `.sdd/epics/*/epic.md` — frontmatter only
- If `.sdd/prds/.design-{feature}.md` exists (from office-hours): auto-load, skip already-answered Phase 1 questions.

#### Phase 1: Premise Challenge

Present (do NOT write anything yet):

```
PREMISE CHALLENGE for '{feature}'

Request as I understand it: [one sentence]
Literal interpretation: [surface feature a junior PM would spec]
Question behind the question: [real job-to-be-done driving this]

Reframe directions:
1. [Reframe #1 — potentially larger or more focused]
2. [Reframe #2 — different angle on same pain point]
3. [Option: "what if we don't build this?"]
```

Ask (max 5 questions): Which direction fits best? Who specifically has this pain? If perfect, what would the user FEEL / STOP doing?

**When answers are weak — push harder:** Vague market → ask for specific task costing 2+ hours/week. Platform vision → ask for smallest version someone would pay for THIS WEEK. Unclear terms → ask for specific step where users drop off.

#### Phase 2: Context Analysis

After user responds, analyze in sub-phases:

- **2A. Existing Solutions** — What already exists that can be reused? Warn about rebuild risk.
- **2B. Overlap Detection** — Check loaded PRDs/epics for semantic overlap, dependencies, conflicts.
- **2C. Dream State** — Current → This feature → Ideal 12-month. On track or diverging?
- **2D. Implementation Alternatives** — Compare approaches (always include 1 minimal + 1 ideal). If `--tech-discovery` enabled, invoke the tech-discovery agent first.
- **2E. 3-Layer Analysis:** Tier 1 (tried-and-true) → Tier 2 (new-and-popular, with skepticism) → Tier 3 (first-principles — where conventional wisdom is wrong for THIS project). Flag `EUREKA:` when Tier 3 reveals a surprising insight.

Ask: "Which approach fits best?" — wait for response before Phase 3.

#### Phase 3: Choose Mode & Deep Analysis

If mode set via flag, skip selection. Otherwise present options:

- **EXPAND** — Dream big, find the 10-star product. For: greenfield, strategic.
- **HOLD** — Scope is right, stress-test it. For: clear requirements.
- **REDUCE** — Strip to essence. For: complex multi-system, time pressure.
- **SELECTIVE EXPANSION** — Keep core scope, cherry-pick specific expansions.

Each mode has its own deep analysis protocol (10x questions, stress test, minimum viable feature, or expansion cherry-picking).

##### Phase 3 → Phase 4 Mid-Flow Checkpoint (FR-3 / AD-6)

On entry to Phase 4, check intra-run process-memory flag `checkpoint_fired`:
- If `checkpoint_fired == true`: skip block (single-fire per invocation).
- If `checkpoint_fired == false`: issue the AskUserQuestion below.

State scope (WARN-4 lock):
- `checkpoint_fired` lives in intra-run process memory ONLY.
- NEVER persisted to disk, env var, frontmatter, or GitHub label.
- Every fresh prd-rethink invocation starts with `checkpoint_fired = false`.
- Re-running prd-rethink on the same feature ALWAYS re-offers the escape valve.

**Verbatim 6-field Decision-Brief (AD-8 / per `conventions.md:282-308`):**

- **D-1 / Mid-flow mode switch (Phase 3 → Phase 4 boundary)**
- **ELI10:** You picked one rethink mode at Phase 1 (expand/hold/reduce/selective). Now that you've done the deep analysis, do you want to keep it, or switch to a different mode while keeping all the findings you've gathered so far?
- **Recommendation:** Continue current mode — Enter-press is a no-op; only switch if your Phase-3 findings clearly contradict the original mode choice.
- **Pros:**
  - Continue: zero re-work; Phase 3 analysis flows directly into Phase 4; default press-Enter path preserves muscle memory
  - Switch to <Y>: discovery findings preserved verbatim; only mode/strategy variable swaps; cheap mid-flow course-correction
  - Switch to <Z>: same preservation guarantee as <Y>; useful when expand-vs-reduce realisation hits mid-flow
- **Cons:**
  - Continue: locks you into a mode that may already feel wrong; restart later costs Phase 1-3 redo
  - Switch to <Y>: Phase 4 protocol diverges per mode — small mental-context switch cost
  - Switch to <Z>: same context-switch cost as <Y>; risk of analysis-paralysis if user toggles modes
- **Net:** Pick Continue because switching mid-flow without strong contradictory findings is more often wasteful than productive — the checkpoint exists for the genuine "I was wrong about the mode" case, not for hedging.

On user response:
- **Continue current mode** (default): set `checkpoint_fired = true`; proceed to Phase 4 unchanged. Empty stderr (NFR-1 byte-identity).
- **Switch to `<Y>`** or **Switch to `<Z>`**:
  - `mode := <new_mode>`
  - Findings: preserve verbatim in run-scratch state (no mutation, no re-derivation).
  - `checkpoint_fired := true`
  - Emit stderr (AD-7 grammar): `prd-rethink: fr3-mode-switch: switched from <X> to <Y>; N findings preserved in scratch`

Stderr emission rule: ONLY on switch. Continue path emits empty stderr.

> **Plain-text fallback:** If `AskUserQuestion` cannot render, emit the plain-text fallback (see `conventions.md` §AskUserQuestion Decision-Brief Format → Plain-text fallback).

#### Phase 4: Lock Decisions & Timing Interrogation

Lock key decisions: problem framing, target user, scope, key bet, out-of-scope list.

Interrogate timing — decisions to answer BEFORE PRD (cheaper now than during implementation):
- Hour 1 (foundation): What does the implementer need immediately?
- Hours 2-3 (core logic): What ambiguity will they hit?
- Hours 4-5 (integration): What surprises will occur?
- Hours 6+ (polish/test): What do you wish you'd planned?

Max 5 decisions, each with recommendation + rationale. Present 2-3 at a time.

#### Phase 5: Create Product Brief

Save to `.sdd/prds/.rethink-{feature}.md`:

**Product-brief schema** (save to `.sdd/prds/.rethink-{feature}.md`):

| name | type | required | example |
|------|------|----------|---------|
| feature | frontmatter | yes | `"auth-revamp"` |
| mode | frontmatter | yes | `"expand\|hold\|reduce"` |
| status | frontmatter | yes | `"ready-for-prd"` |
| problem | text | yes | `"Users abandon onboarding at step 3 because..."` |
| original-vs-new | bullets | yes | `"Original: X / Reframe: Y / Key insight: Z"` |
| target-user | text | yes | `"Primary: [Persona] — [who, when they hit this pain]"` |
| desired-outcome | text | yes | `"What user will FEEL and DO after ship"` |
| scope-decision | bullets | yes | `"IN: [...] / OUT: [...] with reasons"` |
| product-context | text | no | `"Depends on auth-service, conflicts with epic #42"` |
| decisions-made | table | yes | `# / Decision / Choice / Rationale` |
| key-bets-risks | text | yes | `"Bet: [...] / If wrong: [...] / Mitigation: [...]"` |
| prd-scale | text | yes | `"medium — 3 FRs, 2 weeks"` |
| open-questions | list | yes | `"2-5 questions for prd-new to resolve"` |

**Required fields:** feature, mode, status, problem, original-vs-new, target-user, desired-outcome, scope-decision, decisions-made, key-bets-risks, prd-scale, open-questions

#### Phase 6: Post-Creation

1. Confirm: `Product Brief created: .sdd/prds/.rethink-{feature}.md`
2. Brief summary: mode, problem (1 sentence), user, scope, key bet, scale.
3. Next steps: proceed to `team-build` for full doc pipeline.

### Integration with office-hours

When `.sdd/prds/.design-{feature}.md` exists: auto-load in Phase 0, skip already-identified pain points in Phase 1, focus on challenging premises and reframing.

### Context Pressure Protocol

**Never skip:** Phase 1 (Premise Challenge) + Phase 5 (Product Brief).
**Compress:** Phase 2 to one-paragraph summary. Phase 3 to recommendation + 1-sentence reasoning. Phase 4 to 3 decisions as bullets.
**Always generate** the Product Brief file — this is the deliverable.

### Model Tier

Requires `opus` — creative product thinking, nuanced reframing, strategic judgment.

### Mode + Lenses (FR-6/7/8/9)
Step 0 emits D-1 Rethink Mode [scope_expansion|selective_expansion|hold|reduction] → written to brief frontmatter `mode:` (lowercase canonical). Step 0E (Temporal Interrogation) tags each decision NOW/LATER in the Decisions Made table (Timing column). Step 0F walks 4 lenses in fixed order → see [cognitive-lenses.md](cognitive-lenses.md). FR-9 anti-batch: 1 AskUserQuestion per scope finding (strict mode); at ≥10 findings emit one heads-up note, still ask one-by-one. <!-- lint-skip -->

→ See plan-review.md §plan-review

## Workflow

After planning, proceed to [doc.md](doc.md) for the documentation pipeline (PRD writing through epic setup).
