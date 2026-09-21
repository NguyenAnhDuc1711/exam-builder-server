# Execute

Epic autopilot: plan tasks, dispatch agents, track progress, auto-continue. Also covers epic setup.

See [conventions.md](conventions.md) for git workflows, frontmatter, GitHub operations.

## epic-start

Create branch and prepare epic for execution.

### Usage

```
sdd epic-start <epic_name>
```

### Preflight

```bash
source skill/sdd/scripts/gh-helper.sh
epic_name="$1"
test -f .sdd/epics/$epic_name/epic.md || { echo "Epic not found: run sdd prd-parse $epic_name"; exit 1; }
```

### Steps

1. **Auto-commit uncommitted changes:**
   ```bash
   if [ -n "$(git status --porcelain)" ]; then
     git add -A && git commit -m "WIP: auto-commit before epic-start $epic_name"
   fi
   ```

2. **Create or enter branch:**
   ```bash
   if ! git branch -a | grep -q "epic/$epic_name"; then
     git checkout main && git pull origin main
     git checkout -b epic/$epic_name
     git push -u origin epic/$epic_name
   else
     git checkout epic/$epic_name
     git pull origin epic/$epic_name 2>/dev/null || true
   fi
   ```

3. **Initialize epic context** (create only if missing):
   ```bash
   mkdir -p .sdd/context/epics
   ```
   If `.sdd/context/epics/$epic_name.md` does not exist, create it:
   ```markdown
   ---
   epic: {epic_name}
   branch: epic/{epic_name}
   started: {datetime}
   status: in-progress
   ---
   # Epic Context: {epic_name}
   ## Key Decisions
   ## Notes
   ```

4. **Identify ready issues** — read all `[0-9]*.md` in `.sdd/epics/$epic_name/`:
   - **Ready**: `status: open`, no unmet `depends_on`
   - **Blocked**: has unmet dependencies
   - **Complete**: `status: closed`

5. **Display status and suggest next steps:**
   ```
   Epic ready: {epic_name}
     Branch: epic/{epic_name}
     Ready: {N} | Blocked: {N} | Complete: {closed}/{total}

   Next:
     Manual: sdd issue-start {first_ready}
     Auto:   sdd epic-run {epic_name}
   ```

**STOP here.** Do not execute tasks — user decides next action.

---

## epic-sync

Push epic and tasks to GitHub as issues. Canonical home for epic-sync (sourced from former `doc.md:157-208` per AD-6 / FR-1b). Only runs when `GH_AVAILABLE=1`.

### Usage

Invoked inline from the pipeline (no standalone CLI). Preconditions:
- `.sdd/epics/{feature}/epic.md` must exist
- Task files (`[0-9]*.md`) must exist in `.sdd/epics/{feature}/`
- If `.sdd/epics/{feature}/github-mapping.md` already exists, the epic is already synced — skip the entire step.

### Steps

1. **Create epic issue:**

   ```bash
   source skill/sdd/scripts/gh-helper.sh
   check_remote_origin
   REPO=$(get_repo)

   body_file=$(mktemp)
   strip_frontmatter ".sdd/epics/{feature}/epic.md" "$body_file"
   epic_url=$(gh issue create --repo "$REPO" --title "Epic: {feature}" --body-file "$body_file" --label "epic,epic:{feature}")
   epic_number=$(echo "$epic_url" | grep -oE '[0-9]+$')
   rm -f "$body_file"
   ```

2. **Create task issues (sequentially):**

   ```bash
   use_subissues=false
   gh extension list 2>/dev/null | grep -q "yahsan2/gh-sub-issue" && use_subissues=true

   for task_file in .sdd/epics/{feature}/[0-9]*.md; do
     task_name=$(grep '^name:' "$task_file" | head -1 | sed 's/^name: *//')
     model=$(grep '^recommended_model:' "$task_file" | head -1 | sed 's/^recommended_model: *//')
     [ -z "$model" ] && model="sonnet"
     body_file=$(mktemp)
     strip_frontmatter "$task_file" "$body_file"

     if [ "$use_subissues" = true ]; then
       task_url=$(gh sub-issue create --parent "$epic_number" --title "$task_name" --body-file "$body_file" --label "task,epic:{feature},model:$model")
     else
       task_url=$(gh issue create --repo "$REPO" --title "$task_name" --body-file "$body_file" --label "task,epic:{feature},model:$model")
     fi
     rm -f "$body_file"
     # Record old_num:new_num mapping
   done
   ```

3. **Rename task files** to match GitHub issue numbers. Update `depends_on`, `conflicts_with` references, add `github:` field to frontmatter, refresh `updated:` timestamp.

4. **Update epic frontmatter** with `github:` URL and `updated:` timestamp. Update `## Tasks Created` section with real issue numbers.

5. **Create mapping file** at `.sdd/epics/{feature}/github-mapping.md` recording epic number, task `number → URL` mappings, and sync timestamp. If not using sub-issues, append a task checklist to the epic issue body so progress is tracked from the parent issue.

### Exit Criteria

- Epic issue created on GitHub with body = frontmatter-stripped `epic.md`.
- Each task file renamed to `{github-number}.md` with `github:` URL recorded in its frontmatter.
- `github-mapping.md` exists and lists every task.
- Epic `## Tasks Created` table reflects real issue numbers.

### Sandbox

When `GH_AVAILABLE=0`, every `gh` call defers to `gh_or_local` and logs to `.sdd/context/pending-sync.md`. See conventions.md §Sandbox for the full fallback contract.

---

## Plan-Review Apply

After plan-review completes but before epic-run begins task execution, apply review findings to the epic. This runs as part of the orchestration flow (not as a separate command).

### When It Runs

Between epic-start (branch ready) and epic-run's decompose/task-execution. Typically triggered by the build orchestrator after the plan-review gate passes.

### Steps

1. **Read verdict from plan-review frontmatter:**
   ```bash
   review_file=".sdd/epics/${epic_name}/plan-review.md"
   verdict=$(grep '^verdict:' "$review_file" | head -1 | awk '{print $2}')
   critical=$(grep '^critical_gaps:' "$review_file" | head -1 | awk '{print $2}')
   warnings=$(grep '^warnings:' "$review_file" | head -1 | awk '{print $2}')
   ```
   If `review_file` does not exist (step was skipped): skip apply entirely.
   If `verdict` is empty: default to `ready-with-warnings` as fail-safe.

2. **Verdict: `blocked`** — display critical issues from the review, ask user:
   - `fix`: resolve issues, then resume build
   - `skip`: bypass apply, continue to decompose
   - `abort`: stop the build

3. **Verdict: `ready` with 0 critical gaps and 0 warnings** — skip apply, proceed directly.

4. **Verdict: `ready-with-warnings` or warnings > 0:**

   Record epic hash before apply:
   ```bash
   epic_hash_before=$(md5 -q ".sdd/epics/${epic_name}/epic.md" 2>/dev/null || md5sum ".sdd/epics/${epic_name}/epic.md" | awk '{print $1}')
   ```

   Read full `plan-review.md`. Apply recommended changes to `epic.md`:
   - Architecture Decision corrections
   - Task breakdown adjustments (add/remove/reorder tasks)
   - Failure mode additions
   - Dependency graph updates

   After applying, hash-compare:
   ```bash
   epic_hash_after=$(md5 -q ".sdd/epics/${epic_name}/epic.md" 2>/dev/null || md5sum ".sdd/epics/${epic_name}/epic.md" | awk '{print $1}')
   ```

5. **Non-application detection** — if `epic_hash_before == epic_hash_after`:
   Warn that review had findings but epic was not modified. Options:
   - `proceed`: continue to decompose without changes
   - `retry`: re-read plan-review and attempt apply again

---

## epic-run

Full epic autopilot: plan, execute all tasks, track progress.

### Usage

```
sdd epic-run <epic_name> [flags]
```

**Flags:**
- `--dry-run` — show plan, do not execute
- `--sequential` — force sequential execution (no parallel)
- `--confirm` — pause between tasks for user confirmation
- `--start-from <id>` — skip tasks before this ID
- `--max-parallel N` — max concurrent agents (default: 3)
- `--model-override <model>` — force model for all tasks

### Preflight

```bash
source skill/sdd/scripts/gh-helper.sh
epic_name="$1"
test -f .sdd/epics/$epic_name/epic.md || { echo "Epic not found"; exit 1; }

current_branch=$(git branch --show-current)
[ "$current_branch" != "epic/$epic_name" ] && { echo "Not on epic branch. Run: sdd epic-start $epic_name"; exit 1; }
```

### Step 1: Generate Execution Plan

Read all task files in `.sdd/epics/$epic_name/`. For each task, parse frontmatter:
- `status`, `depends_on`, `phase`, `parallel`, `files`, `conflicts_with`, `recommended_model`, `github`

Classify each task:
- **READY**: `status: open`, all dependencies closed
- **BLOCKED**: `status: open`, has unresolved dependencies
- **CLOSED**: `status: closed`

If no READY and no BLOCKED tasks:
```
All tasks complete. Next: sdd epic-verify {epic_name}
```

If no READY but BLOCKED exist:
```
No tasks ready — all remaining are blocked. Check: sdd epic-status {epic_name}
```

### Step 2: Apply Filters

If `--start-from <id>` set: remove READY tasks with number < id.

### Step 3: Display Plan

```
Execution Plan: {epic_name}

| # | Task | Model | Phase | Status |
|---|------|-------|-------|--------|

Ready: {N} | Blocked: {N} | Closed: {N}/{total}
```

If `--dry-run`: display plan and **stop**.

### Step 4: Load Config

```bash
# Defaults
max_parallel=3
graceful_degradation=true

# Override from .sdd/config/epic-run.json if present
if [ -f .sdd/config/epic-run.json ]; then
  # Parse max_parallel, graceful_degradation, model_override
fi

# CLI flags override config
# --max-parallel overrides max_parallel
# --sequential sets max_parallel=1
# --model-override overrides per-task model
```

### Step 5: Artifact Detection (Skip Completed Steps)

→ See doc.md §Artifact Detection (Skip Completed Steps)

### Step 6: Group Tasks into Execution Units

1. Collect READY tasks ordered by phase, then task number
2. If sequential mode: each task is its own unit
3. **Parallel group detection** — within same phase, tasks with `parallel: true`:
   - **File conflict check**: read `files:` and `conflicts_with:` from each task frontmatter
   - If two tasks share a file or one lists the other in `conflicts_with:` -> move later task to sequential
   - Split groups exceeding `max_parallel` into sub-groups
4. Single tasks or `parallel: false` -> sequential unit

Display grouping:
```
Execution groups:
  Group 1: #{num} (sequential, {model})
  Group 2: #{a}, #{b}, #{c} (parallel, 3 tasks)
```

### Step 7: Execute Each Unit

Record timing: `unit_start_time=$(date +%s)`

#### Path A — Sequential (single task)

Display: `[{current}/{total}] Starting: #{num} - {name} ({model})`

Dispatch as subagent with explicit model:

```
Agent(
  description="Epic-run: #{num} {name}",
  subagent_type="general-purpose",
  model="{effective_model}",
  prompt="You are executing task #{num} for epic '{epic_name}'..."
)
```

Where `{effective_model}` = `--model-override` if set, otherwise task's `recommended_model` from frontmatter.

Prompt content:

```
You are executing task #{num} for epic '{epic_name}'.

## Task
Read: .sdd/epics/{epic_name}/{num}.md

## Context
Read handoff: .sdd/context/handoffs/latest.md (if exists)
Read epic context: .sdd/context/epics/{epic_name}.md (if exists)

## Skillbook
→ See context.md §Skillbook YAML Template

## Instructions
1. Read and understand all acceptance criteria
2. Load context from handoff notes
3. Check skillbook matches — apply relevant patterns, avoid known pitfalls
4. Implement the required changes
5. Run verification (tests, lint, build as appropriate)
6. SKILLBOOK EXTRACTION: If solving this task required >=2 failed attempts, extract pitfall entry per context.md §Skillbook YAML Template
7. Write handoff to .sdd/context/handoffs/latest.md
   Include: what was done, decisions, files changed, warnings for next task
8. Update task frontmatter: status: closed, updated: {datetime}
9. Commit: Issue #{num}: {description}
10. Close GitHub issue (if gh available):
    gh issue close {github_num} --repo {REPO} --comment "Completed via epic-run"
11. Return concise summary (max 200 words):
    status, files changed, key decisions, warnings, skillbook entries added (if any)
```

**Sandbox fallback:** If `GH_AVAILABLE=0`, skip GitHub close. The agent should:
- Still update local task status to `closed`
- Log the pending close to `.sdd/context/pending-sync.md`
- Continue execution normally

**Graceful degradation:** If subagent dispatch fails and `graceful_degradation=true`, execute inline (read task, implement, commit, close).

Display result: `[{current}/{total}] #{num}: {name} ({model}, {duration})`

#### Path B — Parallel (2+ tasks, no file conflicts)

Display: `[{start}-{end}/{total}] Parallel group: #{a}, #{b}, #{c}`

Dispatch **all tasks simultaneously** — each as separate Agent call in the **same message**, with explicit model per task:

```
Agent(
  description="Epic-run: #{num_a} {name_a}",
  subagent_type="general-purpose",
  model="{effective_model_a}",
  isolation="worktree",
  prompt="You are executing task #{num_a} for epic '{epic_name}'..."
)
Agent(
  description="Epic-run: #{num_b} {name_b}",
  subagent_type="general-purpose",
  model="{effective_model_b}",
  isolation="worktree",
  prompt="You are executing task #{num_b} for epic '{epic_name}'..."
)
```

**Critical:** all Agent calls for a parallel group MUST be in the same message for concurrent execution. Each task may have a different model from its `recommended_model` field.

Prompt content per task:

```
You are executing task #{num} for epic '{epic_name}'.

## Task
Read: .sdd/epics/{epic_name}/{num}.md

## Skillbook
→ See context.md §Skillbook YAML Template

## Instructions
1. Read acceptance criteria from task file
2. Check skillbook matches — apply relevant patterns, avoid known pitfalls
3. Implement changes in your assigned files only
4. Run verification
5. SKILLBOOK EXTRACTION: If >=2 failed attempts before success, extract pitfall per context.md §Skillbook YAML Template
6. Commit: Issue #{num}: {description}
7. Close GitHub issue (if gh available)
8. Return summary: files modified, what was implemented, any issues, skillbook entries added
```

Wait for all agents to complete. Display per-task results:
```
  #{a}: Done
  #{b}: Done
  #{c}: Failed: {error}
```

**Graceful degradation:** If parallel dispatch fails, fall back to sequential (Path A) for remaining tasks in the group.

### Step 8: Self-Regulation

After each task/group, scan result for risk signals:

| Signal | Score | Detection |
|--------|-------|-----------|
| git revert/reset in output | +15% each | grep for `git revert\|git reset` |
| Test failures | +10% each | grep for `FAIL\|failed\|test error` |
| Scope drift (files outside task's `files:`) | +5% per file | compare `git diff --name-only HEAD~1 HEAD` with task's `files:` |

Display: `Risk: {score}% [revert:{N} test-fail:{N} scope:{N}]`

**If risk > 30%** — pause and ask:
- **continue**: reset score to 0, proceed
- **pause**: save state, exit (resume with `--start-from <next>`)
- **abort**: go to completion summary

### Step 9: Re-Plan After Each Unit

Re-scan task files to discover newly unblocked tasks. If new READY tasks found, group them (Step 6) and continue.

### Step 10: Error Handling

#### Error Classification

Classify failures before choosing a response:

**Transient errors** (auto-retry once):
- Network errors, rate limits, `ECONNREFUSED`, timeouts, lock contention
- Detection: scan agent result for keywords `network`, `rate limit`, `ECONNREFUSED`, `lock`, `timeout`
- On transient detection: retry the task once automatically. If retry fails, fall through to failure menu.

**Permanent errors** (immediate failure menu):
- Compilation errors, missing dependencies, logic failures, test failures
- Any error that persists after one automatic retry

#### Failure Menu

**Sequential failure:**

Stop execution. Display progress and error summary:
```
Task #{num} failed: {error_description}
  Completed: {N}/{total} | Failed on: #{num} - {name}
```

Options:
- `fix`: save state, exit. User fixes the issue and resumes with `--start-from <task>`
- `skip`: mark task as skipped, advance to next unit. Task remains `status: open` for later.
- `abort`: go to completion summary with partial results

**Parallel group failure:**

Let all running agents finish (do not abort siblings). Report per-task results, then for each failed task offer: retry (sequentially) / skip / abort.

#### Retry Logic

- Transient errors: 1 automatic retry with fresh agent context
- Permanent errors: no auto-retry, enter failure menu immediately
- Manual retry (`fix` option): user fixes code, then resumes via `--start-from`

### Step 11: Completion Summary

Calculate total duration from `epic_start_time`. Re-scan tasks for final counts.

Display: per-task table (task number, name, model, duration, result), total time, tasks completed vs total, tasks remaining blocked.

Suggest next steps:
- All done: `sdd epic-verify {epic_name}`
- More tasks: `sdd epic-run {epic_name}` (re-run for newly unblocked)
- Check status: `sdd epic-status {epic_name}`

---

## Progress Tracking

During execution, progress is tracked in:

- **Task frontmatter**: `status: closed`, `updated: {datetime}` — source of truth
- **Handoff notes**: `.sdd/context/handoffs/latest.md` — context for next task
- **Epic context**: `.sdd/context/epics/{epic_name}.md` — decisions and history
- **Epic progress**: `.sdd/context/progress/{epic_name}.md` — completion stats per epic
- **Pending sync**: `.sdd/context/pending-sync.md` — GitHub ops logged when `gh` unavailable

### Handoff Note Format

Written by each task agent after completion:

```markdown
# Handoff: Task #{num}
## What Was Done
{summary of changes}
## Decisions Made
{key decisions and rationale}
## Files Changed
{list of files}
## Warnings for Next Task
{gotchas, incomplete items, dependencies}
```

---

## epic-oneshot

**epic-oneshot:** Skip qa + plan-review gates; otherwise identical to office-hours → team-build pipeline. See doc.md §team-build for the canonical orchestration.

---

## epic-refresh

**epic-refresh:**
- Trigger: PRD or epic.md changed after task files exist.
- Re-reads: prd.md, epic.md.
- Overwrites: task files in `.sdd/epics/{feature}/` (preserves frontmatter status).
- State: re-runs decompose with diff-aware merge.
- Rollback: `git checkout HEAD -- .sdd/epics/{feature}/`.

---

→ See conventions.md §Sandbox
