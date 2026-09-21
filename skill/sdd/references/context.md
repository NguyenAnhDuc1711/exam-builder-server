# Context Management

Project documentation lifecycle: create baseline docs, load context for sessions, update incrementally.

See [conventions.md](conventions.md) for shared rules (frontmatter, paths, datetime).

## Context Files

All files live in `.sdd/context/`. Created by `ctx-create`, loaded by `ctx-prime`, maintained by `ctx-update`.

### Core Files (9)

| File | Purpose | Update Frequency |
|------|---------|-----------------|
| `progress.md` | Current status, completed work, next steps | Always |
| `project-structure.md` | Directory layout, file organization | If structure changed |
| `tech-context.md` | Dependencies, frameworks, dev tools | If deps changed |
| `system-patterns.md` | Architecture patterns, design decisions | If architecture changed |
| `product-context.md` | User personas, core features, use cases | If requirements changed |
| `project-brief.md` | Scope, goals, success criteria | Rarely |
| `project-overview.md` | Feature list, capabilities, integrations | Major milestones |
| `project-vision.md` | Long-term direction, strategic priorities | Rarely |
| `project-style-guide.md` | Coding standards, naming conventions | If conventions changed |

### Extended Files

These files are maintained by other references but loaded by `ctx-prime`:

| File | Maintained By | Purpose |
|------|--------------|---------|
| `skillbook.md` | [work.md](work.md) | Accumulated patterns and past solutions |
| `active-interfaces.md` | Epic-specific | API contracts for current epic |
| `progress-archive.md` | `ctx-update` | Archived progress entries |

### Subdirectories

```
.sdd/context/
  build-state/     # Build progress tracking (JSON)
  epics/           # Epic context files
  handoffs/        # Task handoff notes
  sessions/        # Debug journals (local-only)
  sync/            # Sync state
  verify/          # Verification state and reports
```

---

## ctx-create

Create initial project context documentation. Run once per project, after `init`.

### Preflight

```bash
# 1. Check existing context
if ls .sdd/context/*.md >/dev/null 2>&1; then
  count=$(ls -1 .sdd/context/*.md | wc -l | tr -d ' ')
  # Ask user: "Found $count context files. Overwrite? (yes/no)"
  # If no → suggest ctx-update instead. Stop.
fi

# 2. Ensure directory exists
mkdir -p .sdd/context 2>/dev/null

# 3. Get current datetime
CREATED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

### Project Analysis

Gather project information before creating files:

**1. Detect project type:**

| Config File | Project Type |
|------------|-------------|
| `package.json` | Node.js |
| `requirements.txt`, `pyproject.toml` | Python |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| `pom.xml`, `build.gradle`, `build.gradle.kts` | Java/Kotlin |
| `*.sln`, `*.csproj` | .NET |
| `Gemfile` | Ruby |
| `composer.json` | PHP |
| `pubspec.yaml` | Dart/Flutter |
| `Package.swift` | Swift |
| `CMakeLists.txt` | C/C++ |

```bash
find . -maxdepth 2 \( -name 'package.json' -o -name 'requirements.txt' -o -name 'pyproject.toml' \
  -o -name 'Cargo.toml' -o -name 'go.mod' -o -name 'pom.xml' -o -name 'build.gradle' \
  -o -name 'build.gradle.kts' -o -name '*.sln' -o -name '*.csproj' -o -name 'Gemfile' \
  -o -name 'composer.json' -o -name 'pubspec.yaml' -o -name 'Package.swift' \
  -o -name 'CMakeLists.txt' \) 2>/dev/null
```

**2. Git information:**

```bash
git remote -v 2>/dev/null
git branch --show-current 2>/dev/null
git log --oneline -10 2>/dev/null
```

**3. Codebase scan:**

- Read `README.md` if exists
- Run `ls -la` for root structure
- Scan for source files: `find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.py' -o -name '*.rs' -o -name '*.go' -o -name '*.java' -o -name '*.rb' -o -name '*.swift' -o -name '*.sh' \) 2>/dev/null | head -20`
- Check for tests: `find . \( -path '*/.*' -prune \) -o \( -type d \( -name 'test' -o -name 'tests' -o -name '__tests__' \) -o -type f \( -name '*test*' -o -name '*spec*' \) \) -print 2>/dev/null | head -10`

### File Creation

Create each of the 9 core files with frontmatter per [conventions.md](conventions.md):

```yaml
---
created: {CREATED}
last_updated: {CREATED}
version: 1.0
author: Claude Code PM System
---
```

**Per-file content guidance:**

- **progress.md** — Current branch, recent commits (last 5-10), outstanding changes, immediate next steps
- **project-structure.md** — Key directories, file naming patterns, module organization, entry points
- **tech-context.md** — Language/framework versions, all dependencies with versions, dev tools, build system
- **system-patterns.md** — Design patterns observed, architectural style, data flow, error handling approach
- **product-context.md** — What users do with this, core features, use cases, user personas
- **project-brief.md** — What it is, why it exists, goals, success criteria
- **project-overview.md** — Feature list with status, capabilities, integration points
- **project-vision.md** — Long-term goals, strategic direction, potential expansions
- **project-style-guide.md** — Naming conventions, file structure patterns, comment style, linting rules

### Validation

After creating each file:
- Verify file exists and is non-empty (minimum 10 lines)
- Check frontmatter starts with `---` and contains `created` field
- If any file fails: report which succeeded, offer to continue with partial context

### README.md Regeneration

After all context files are created:

1. Read context files: `project-overview.md`, `project-brief.md`, `tech-context.md`, `project-structure.md`
2. Read existing `README.md` if present — preserve manually-maintained sections (Contributing, License, etc.)
3. Generate `README.md` at project root with: name, description, features, tech stack, getting started, project structure
4. Write to project root

### Summary

```
Context created: .sdd/context/
Files: {count}/9 | Project: {type} | Language: {lang}
Next: ctx-prime to load context in new sessions
```

---

## ctx-prime

Load project context for a new session. Read-only — no files modified.

### Preflight

```bash
# 1. Check context exists
if ! ls .sdd/context/*.md >/dev/null 2>&1; then
  echo "No context found. Run ctx-create first."
  # Stop.
fi

# 2. Count files
count=$(ls -1 .sdd/context/*.md 2>/dev/null | wc -l | tr -d ' ')

# 3. File integrity — for each .md file:
#    - test -r (readable)
#    - test -s (non-empty)
#    - head -1 should be '---' (frontmatter present)
#    Skip files that fail with warning.

# 4. Git state
git status --short 2>/dev/null
git branch --show-current 2>/dev/null
```

### Loading Sequence

Load context files in priority order:

**Priority 1 — Essential (load first):**
1. `project-overview.md` — high-level understanding
2. `project-brief.md` — core purpose and goals
3. `tech-context.md` — technical stack and dependencies

**Priority 2 — Current State (load second):**
4. `progress.md` — current status and recent work
5. `project-structure.md` — directory and file organization

**Priority 3 — Deep Context (load third):**
6. `system-patterns.md` �� architecture and design patterns
7. `product-context.md` — user needs and requirements
8. `project-style-guide.md` — coding conventions
9. `project-vision.md` — long-term direction

**Extended (load if present):**
10. `skillbook.md` — accumulated patterns and known solutions
11. `active-interfaces.md` — API contracts for current epic

### Frontmatter Validation

For each file loaded, check:
- `created` date is valid ISO 8601
- `last_updated` >= `created`
- `version` is present

If frontmatter is invalid: note the issue but continue loading content.

### Supplementary Information

After loading context files:
- Read `README.md` at project root (if exists)
- Check for `.env.example` for environment setup needs
- Run `git ls-files --others --exclude-standard | head -20` for untracked files

### Error Recovery

| Missing File | Fallback |
|-------------|----------|
| `project-overview.md` | Read README.md instead |
| `tech-context.md` | Analyze config files directly (package.json, Cargo.toml, etc.) |
| `progress.md` | Run `git log --oneline -10` for recent status |
| Any other | Note as missing, continue with available context |

If fewer than 3 files load: suggest running `ctx-create` for full rebuild.

### Summary

```
Context primed: {success}/{total} files loaded
  Essential: {n}/3 | Current: {n}/2 | Deep: {n}/4
Project: {name} | Branch: {branch} | Status: {from progress.md}
```

---

## ctx-update

Update context documentation to reflect current project state. Run at end of development sessions.

### Preflight

```bash
# 1. Verify context exists
if ! ls .sdd/context/*.md >/dev/null 2>&1; then
  echo "No context to update. Run ctx-create first."
  # Stop.
fi

# 2. Get current datetime
UPDATED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# 3. Detect changes
git status --short
git log --oneline -10
git diff --stat HEAD~5..HEAD 2>/dev/null
```

### Change Detection

Check what has changed since last update:

```bash
# Structural changes
git diff --name-status HEAD~10..HEAD 2>/dev/null | grep -E '^A' | head -20

# Dependency changes — check for diffs in config files:
# package.json, requirements.txt, pyproject.toml, Cargo.toml, go.mod,
# pom.xml, build.gradle, composer.json, pubspec.yaml, Gemfile, CMakeLists.txt
for f in package.json requirements.txt pyproject.toml Cargo.toml go.mod \
         pom.xml build.gradle composer.json pubspec.yaml Gemfile CMakeLists.txt; do
  git diff HEAD~5..HEAD "$f" 2>/dev/null
done
```

### Per-File Update Strategy

| File | When to Update | What to Check |
|------|---------------|--------------|
| `progress.md` | **Always** | Recent commits, current branch, blockers, next steps |
| `project-structure.md` | New files/dirs added | `git diff --name-status` for additions |
| `tech-context.md` | Dependencies changed | Config file diffs |
| `system-patterns.md` | Architecture changed | New patterns, refactoring, design decisions |
| `product-context.md` | Requirements changed | New features, user feedback incorporated |
| `project-brief.md` | **Rarely** | Only if fundamental goals changed |
| `project-overview.md` | Major milestones | Feature completion, new capabilities |
| `project-vision.md` | **Rarely** | Only for strategic direction shifts |
| `project-style-guide.md` | Conventions changed | New linting rules, pattern adoptions |

### Smart Update Rules

For each file that needs updating:

1. **Read existing content** — understand current state
2. **Identify specific sections** to update — don't rewrite entire file
3. **Preserve frontmatter** — update only `last_updated` and optionally `version`:
   ```yaml
   last_updated: {UPDATED}
   version: {increment minor for significant changes, e.g. 1.0 → 1.1}
   ```
4. **Make targeted edits** — surgical changes, not full regeneration
5. **Skip unchanged files** — preserve accurate timestamps

### Auto-Archive Progress

If `progress.md` has more than 3 `###` entries under "Completed Work":

1. Read `.sdd/context/progress-archive.md` (create if missing, with frontmatter)
2. Move older entries (keep only 3 most recent in `progress.md`)
3. Append moved entries to `progress-archive.md`
4. Add link in `progress.md`: `> Older entries: see progress-archive.md`

### README.md Sync

If any context files were updated in this run:

0. **Atomic backup (FR-1 / R-1 mitigation):** Before any regen, `cp README.md README.md.bak`.
   On copy failure (disk full, permission denied), emit stderr
   `ctx-update: fr1-user-section-preserve: backup failed: <reason>` and exit non-zero
   WITHOUT overwriting README.md. Mirrors `scripts/init.sh:64` precedent for CLAUDE.md.bak.

1. **Paired-marker scan (AD-3 / R-8 mitigation):** Scan `README.md` for paired user-section markers:
   - Opening: `<!-- sdd:user-section v1 -->`
   - Closing: `<!-- /sdd:user-section -->`
   - Karpathy parity per `scripts/init.sh:43,54` (versioned, two-tag delimited).
   - Scanner MUST track fenced-code-block state via ``` toggle. Markers inside fenced
     code blocks are IGNORED (R-8 mitigation — prevents code-fence false-positive).
   - Unmatched opening without closing tag = parse error → emit
     `ctx-update: fr1-user-section-preserve: unmatched opening tag at line N` and abort regen.
   - Preserved region = inclusive of both markers + body between them.

2. **Canonical-list-miss secondary heuristic:** Canonical SDD sections are
   Overview, Quick Start, Workflow, Architecture, Commands, Configuration, Testing.
   Section titles outside this list = candidate user-authored (secondary detection).
   Heuristic-detected sections are NOT auto-rewrapped — only counted toward the >50% threshold.

3. **Fail-loud emission (AD-7 grammar, happy-path carve-out):** When ≥1 marked section
   detected, emit stderr:
   `ctx-update: fr1-user-section-preserve: preserving N section(s): <comma-separated titles>`
   NEVER emit when N=0 (happy-path NFR-1 byte-identity).

4. **6-field Decision-Brief AskUserQuestion gate (AD-8):** When >50% of detected sections
   are canonical-list-miss (not markered, not in canonical list), present the verbatim
   6-field Decision-Brief (per `conventions.md:282-308`):

   - **D-1 / Preserve user-authored README sections**
   - **ELI10:** Your README has sections that don't match the SDD template. The default
     behavior would overwrite them. We can preserve them, walk through each one with you,
     or skip the regen entirely.
   - **Recommendation:** Preserve all — protects user content; .bak provides traceability.
   - **Pros:**
     - Preserve all: zero data loss; original README byte-identical post-run; .bak gives audit trail
     - Review each: per-section control; user picks which sections to keep vs regen; precise outcome
     - Skip regen: cleanest exit; user fixes README manually and re-runs when ready
   - **Cons:**
     - Preserve all: README does not pick up template improvements until user wraps sections in markers
     - Review each: highest friction; N user prompts where N is section count; tedious for large READMEs
     - Skip regen: leaves stale README until user takes manual action; context drift continues
   - **Net:** Pick Preserve all as default — silent data loss is the worst outcome; user content
     trumps template freshness; .bak gives recovery path if user wants to merge later.

   Options:
   - **Preserve all** (default): short-circuit regen.
   - **Review each**: per-section confirmation; only confirmed sections written.
   - **Skip regen**: exit non-zero.

5. **Bypass-overwrite guard (R-9 mitigation):**
   - "Preserve all" → DO NOT write a regenerated README. Exit silently with current README intact.
     (.bak gives traceability; README is unchanged.)
   - "Review each" → per-section confirmation; only confirmed sections are written.
   - "Skip regen" → exit non-zero with stderr line
     `ctx-update: fr1-user-section-preserve: user declined regen`.

6. **Standard sync (when no markers + ≤50% canonical-list-miss):** Update only sections
   that correspond to changed context:
   - `project-overview.md` changed → update Features section
   - `tech-context.md` changed → update Tech Stack / Installation
   - `project-structure.md` changed → update Project Structure

   Preserve all other sections unchanged.

If no context files changed: skip README update.

### Error Handling

- File locked or unwritable → skip with warning, continue others
- Corrupted frontmatter → preserve file, log warning
- Never leave files in corrupted state — if write fails, keep original

### Summary

```
Context updated: {updated}/{total} files
  Updated: {list of updated files}
  Skipped: {count} (no changes)
Timestamp: {UPDATED}
Next: ctx-prime to reload in next session
```

---

## Memory Agent Automation

Automated memory lifecycle — patterns are captured, stored, and surfaced without manual commands.

### When Memory Saves (triggers)

Memory saves are side-effects of other operations. They never block the parent operation — failures are logged and skipped.

| Trigger | What is Saved | Condition |
|---------|--------------|-----------|
| `issue-complete` (knowledge extract) | Reusable patterns, pitfalls, root-cause analyses | `--no-learn` flag not set |
| `issue-complete` (memory ingest) | Structured task summary: decisions, blockers, lessons | `memory_agent.enabled` and `memory_agent.auto_ingest` both true |
| `epic-verify` | Lessons learned across the epic: recurring failures, effective approaches | Epic has completed tasks |
| Debug journal archive | Debugging patterns that worked/failed, root cause chains | Journal exists for the issue |

### What to Save

Each memory entry captures one of:
- **Helpful pattern** — an approach that worked well and is reusable
- **Pitfall** — a mistake or dead-end to avoid in similar contexts
- **Architectural decision** — a design choice with rationale
- **Tool-specific learning** — framework quirks, API gotchas, config nuances

Quality filter: only save entries that would help a future session working on similar code. Generic observations ("tests are important") are not worth capturing.

### Skillbook YAML Template

Entries written to `.sdd/context/skillbook.md` use this structure per entry:

```yaml
---
id: SKL-{sequential}
pattern: helpful | pitfall
context: {comma-separated keywords, 3-6, technology/domain focused}
source_task: {epic_name}#{issue_number}
memory_ids: []
created: {ISO 8601 datetime}
last_matched: null
match_count: 0
---
**Pattern:** {one-liner description}
**Why:** {root cause or importance}
**When applicable:** {trigger conditions}
**Resolution:** {how to fix or apply}
```

### Memory Ingest Flow

When `memory_agent.enabled` and `memory_agent.auto_ingest` are true in `.sdd/config/lifecycle.json`:

1. Check agent health (HTTP ping, max 5s timeout)
2. Build structured summary from task file + handoff note
3. POST to `http://{host}:{port}/ingest` with `source: "issue-complete-#{N}"`
4. If any step fails: set status to offline, continue without blocking

---

## Skillbook Management

The skillbook (`.sdd/context/skillbook.md`) accumulates reusable patterns extracted from completed work, machine-maintained via five features: **Auto-Extraction** harvests patterns during `issue-complete`; **Loading** injects relevance-filtered entries into other commands; **Pruning** drops stale/contradicted/duplicate entries; **Auto-Promote** elevates high-confidence memory-agent insights; **Dedup** prevents redundant appends. File structure is YAML entries separated by `---` fences with sequential IDs (`SKL-001`, ...) — see §Skillbook YAML Template above. All features are non-blocking: failures (extractor returns nothing, memory agent offline, prune candidate ambiguous) skip silently and let issue completion continue.

| Feature | Trigger | Output | Reference |
|---------|---------|--------|-----------|
| Auto-Extraction | `issue-complete` (Step 3 Knowledge Extract, Step 5 Learning Extraction) — gathers debug journal, changed files, issue body; analyzes for 0-3 reusable patterns per task | `append_skillbook_entry(pattern_type, context_keywords, source_task, body)` — `pattern_type` is `helpful` or `pitfall` | §Skillbook YAML Template |
| Loading | `ctx-prime` (Priority "Extended", after core 9), `issue-new` (filtered scan vs description), `issue-start` (filtered vs issue scope), `epic-run` (filtered per task vs task domain) | Max 3 relevance-filtered entries injected per point; filter = `context` keyword overlap with current scope | §Skillbook YAML Template |
| Pruning | Scheduled cleanup or on-demand. Criteria: never-matched (`match_count: 0`, older than configurable task count, default 20) → remove; contradicted (newer entry with same `context` supersedes) → remove older; duplicate (same `context` + overlapping body) → merge, sum `match_count` | Rewritten skillbook with contiguous IDs re-sequenced (`SKL-001`, `SKL-002`, ...); interactive mode confirms, batch mode auto-prunes | §Skillbook YAML Template |
| Auto-Promote | Memory-agent consolidation surfaces insight with `confidence >= 0.7` AND type `pattern_repetition` or `recurring_pain_point`. Queried during `ctx-prime` / `issue-complete` via `GET /query?type=pattern&format=json&limit=5` | New entry with `pattern: pitfall` (pain points) or `helpful` (repetitions); `source_task: memory-promote`; `memory_ids: [...]` for backlink-to-memory deep-dive | §Skillbook YAML Template |
| Dedup | Before any append: compare `context` keywords (>80% overlap) AND/OR body text (semantic equivalence) against existing entries | If duplicate: increment `match_count` on existing entry, update `last_matched`, skip append. If unique: append fresh entry | §Skillbook YAML Template |

---

## Context Health

Automated checks to ensure context files remain valid and current.

### Health Checks

Run as part of `ctx-prime` preflight and optionally during `ctx-update`:

| Check | What | Action on Failure |
|-------|------|------------------|
| Existence | Each core file in `.sdd/context/` exists | Warn, suggest `ctx-create` if <3 files present |
| Non-empty | Each file has >0 bytes | Warn, skip file during load |
| Frontmatter | File starts with `---` and contains `created` field | Warn, load content anyway |
| Readable | `test -r` passes | Skip file with error |

### Staleness Detection

| File | Stale Threshold | Detection Method |
|------|----------------|-----------------|
| `progress.md` | 7 days without update | Compare `last_updated` to current date |
| `tech-context.md` | Config files changed since `last_updated` | Diff config files against timestamp |
| `system-patterns.md` | Major refactoring since `last_updated` | Check `git diff --stat` for architectural files |
| `skillbook.md` | No new entries in 30+ days despite task completions | Compare latest `created` entry to recent commits |
| Other core files | 30 days without update | Compare `last_updated` to current date |

When stale files are detected during `ctx-prime`:
```
Warning: {N} context file(s) may be stale:
  - progress.md (last updated: {date}, {days} days ago)
  - tech-context.md (dependencies changed since last update)
Suggest: ctx-update to refresh
```

### Auto-Repair

When context files are missing or corrupted, automated recovery applies:

| Condition | Recovery |
|-----------|---------|
| `progress.md` missing | Generate from `git log --oneline -10` and current branch |
| `tech-context.md` missing | Analyze config files (package.json, Cargo.toml, etc.) directly |
| `project-structure.md` missing | Run `ls -la` and `find` to rebuild directory layout |
| Frontmatter corrupted | Regenerate frontmatter block, preserve file body |
| `skillbook.md` missing | Create empty skillbook with header (no entries lost — entries come from future tasks) |
| Any other file missing | Note as missing, continue with available context |

Auto-repair runs only when explicitly triggered (by `ctx-prime` detecting issues) — it does not modify files silently in the background.
