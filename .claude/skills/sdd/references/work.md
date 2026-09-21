# Work

Light path for standalone issues: create, start, complete. For bugs, small tasks, and enhancements that don't need the full PRD ceremony.

See [conventions.md](conventions.md) for git workflows, frontmatter, GitHub operations.

## issue-new

Create a new issue with investigation and planning.

### Usage

```
sdd issue-new <description>
```

### Preflight

```bash
source skill/sdd/scripts/gh-helper.sh
[ -z "$1" ] && { echo "Usage: sdd issue-new <description>"; exit 1; }
mkdir -p .sdd/context/sessions 2>/dev/null
```

### Step 1: Context Loading

Read if they exist (skip silently if missing):
- `.sdd/context/tech-context.md` — tech stack
- `.sdd/context/system-patterns.md` — architecture patterns

Quick scan: read `package.json` / `Cargo.toml` / `go.mod` or equivalent to identify language and framework.

**Skillbook check**: Read `.sdd/context/skillbook.md` if it exists. Scan entry `context` keywords against the issue description keywords. If any entry matches, note it briefly in the plan output (e.g., "Related skillbook pattern: SKL-005 — async blocking in event loop"). Do not include full skillbook content in the plan. Skip silently if no matches.

Summarize only points relevant to the description (1-3 bullets max).

### Step 2: Interactive Scoping

Ask the user:
```
Where should I start looking?
  - File path, class name, function name, or error message
  - Or say "search" and I'll grep for keywords from your description
```

**Progressive scan** — track files read, hard cap at 30:

**Level 0 — Entry point:**
- Read file(s) the user specified, or grep for keywords (top 3-5 matches)
- Form initial hypothesis

**Level 1 — Direct dependencies:**
- Scan imports/requires in Level 0 files
- Read only files relevant to hypothesis

**Level 2 — Dependents (only if needed):**
- Grep for files referencing Level 0-1 files
- Read only if affected by the change

After scanning:
```
Scan complete: {N}/30 files examined
Key findings:
- {finding 1}
- {finding 2}
```

### Step 3: Complexity Assessment

| Level | Criteria | Branch Strategy |
|-------|----------|-----------------|
| LOW | 1-3 files, clear fix, config change | `direct` (commit to current branch) |
| MEDIUM | 3-5 files, needs tests, logic change | `branch` (create feature branch) |
| HIGH | >5 files, >3 modules, schema change | Suggest PRD redirect |

Display:
```
Complexity: {LOW|MEDIUM|HIGH}
  Files: {N} | Modules: {list}
  Branch strategy: {direct|branch}
```

If HIGH: suggest `sdd prd-new <name>` and ask if user wants to continue with light path.

### Step 4: Plan Generation

Generate a plan with these sections:

```markdown
## {Root Cause Hypothesis (bugs) | Objective (enhancements)}
{cause based on code evidence, or what we're adding}

## Approach
{1-3 sentences}

## Files to Change
- `path/file` — {what and why}

## Test Strategy
- {tests to add/modify}

## Risk
{1 sentence}

## Branch Strategy
{direct|branch}
```

Suggest labels: `type:{bug|enhancement|chore|docs}`, `complexity:{low|medium|high}`, `priority:{P0|P1|P2}`, `source:issue-new`.

Wait for user confirmation of plan and labels.

### Step 5: Create Issue

**If `GH_AVAILABLE=1`:**

```bash
check_remote_origin
REPO=$(get_repo)

# Write plan to temp file
body_file="/tmp/issue-new-body-$$.md"
# Write plan content to body_file

title="[{type}] {concise description}"
labels="type:{type},complexity:{complexity},priority:{priority},source:issue-new"

issue_number=$(gh issue create --repo "$REPO" --title "$title" --body-file "$body_file" --label "$labels" | grep -o '[0-9]*$')
rm -f "$body_file"
```

**If `GH_AVAILABLE=0` (sandbox fallback):**

```bash
existing=$(ls .sdd/epics/standalone/issue-*.md 2>/dev/null | wc -l | tr -d ' ')
issue_number=$((existing + 1))
mkdir -p .sdd/epics/standalone
# Write frontmatter (name, title, type, complexity, priority, status: open,
# created/updated timestamps, labels) + plan content body
cat > .sdd/epics/standalone/issue-${issue_number}.md <<EOF
---
name: issue-${issue_number}
title: {title}
status: open
created: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
updated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
---
{plan content}
EOF
gh_or_local issue create  # logs to pending-sync
```

### Output

```
Created Issue #{issue_number}
  Title: {title}
  Labels: {labels}
  Link: {github_url or local_path}

Next: sdd issue-start #{issue_number}
```

**STOP.** Do not continue to work on the issue.

---

## issue-start

Begin work on an issue — load context, set up task.

### Usage

```
sdd issue-start <issue_number>
```

### Preflight

```bash
source skill/sdd/scripts/gh-helper.sh
issue_num="$1"
[ -z "$issue_num" ] && { echo "Usage: sdd issue-start <issue_number>"; exit 1; }
```

### Step 1: Load Issue

**If `GH_AVAILABLE=1`:**
```bash
REPO=$(get_repo)
gh issue view $issue_num --repo "$REPO" --json state,title,labels,body
```

**If `GH_AVAILABLE=0`:**
```bash
# Try local task files
task_file=$(ls .sdd/epics/*/$(printf '%s' "$issue_num").md 2>/dev/null | head -1)
[ -z "$task_file" ] && task_file=$(ls .sdd/epics/standalone/issue-${issue_num}.md 2>/dev/null)
[ -z "$task_file" ] && { echo "Issue #$issue_num not found locally or on GitHub"; exit 1; }
```

**Detect light path:** check if issue has `source:issue-new` label or is in `standalone/` directory.

### Step 2: Determine Branch Strategy

```bash
current_branch=$(git branch --show-current)

if echo "$current_branch" | grep -q "^epic/"; then
  BRANCH_STRATEGY="direct"   # Always direct on epic branch
else
  # Parse from issue body: <!-- branch-strategy: {direct|branch} -->
  # Default: direct
fi
```

If `branch` strategy:
```bash
git checkout -b "fix/issue-$issue_num"
```

### Step 3: Context Loading

Read these if they exist (skip silently if missing):

1. **Previous handoff**: `.sdd/context/handoffs/latest.md` — summarize key points
2. **Epic context**: `.sdd/context/epics/{epic_name}.md` — epic-level decisions
3. **Task file**: `.sdd/epics/{epic_name}/${issue_num}.md` — acceptance criteria
4. **Skillbook**: `.sdd/context/skillbook.md` — scan each entry's `context` keywords against the issue title, description, and files mentioned. Surface top 3 matching entries as "Known patterns to consider." Skip silently if no matches or file missing.

**For light path issues:** the issue body IS the plan. No separate analysis needed.

### Step 4: Debug Journal (light path only)

If this is a light-path bug investigation, create `.sdd/context/sessions/issue-${issue_num}-debug.md` with header (issue number, title, datetime, mode: semi-auto). Append rounds as work progresses: `## Round {N}` with Hypothesis, Action, Result (PASS/FAIL), Notes.

### Step 5: Setup Progress Tracking

```bash
mkdir -p .sdd/context/progress 2>/dev/null
```

Update task frontmatter: `status: in-progress`, `updated: {datetime}`.

### Step 6: GitHub Assignment

**If `GH_AVAILABLE=1`:**
```bash
check_remote_origin
gh issue edit $issue_num --repo "$REPO" --add-assignee @me --add-label "in-progress"
```

**If `GH_AVAILABLE=0`:** update local task frontmatter only. Log to pending-sync.

### Output

```
Started work on issue #{issue_num}
  Branch: {current_branch}
  Strategy: {direct|branch}

Workflow:
  1. Implement the changes
  2. Complete: sdd issue-complete {issue_num}
```

**STOP.** Do not implement — user decides next action.

---

## issue-complete

Finish work: validate, verify, close.

### Usage

```
sdd issue-complete <issue_number>
```

### Preflight

```bash
source skill/sdd/scripts/gh-helper.sh
issue_num="$1"
[ -z "$issue_num" ] && { echo "Usage: sdd issue-complete <issue_number>"; exit 1; }
```

### Step 1: Handoff Validation

Check that a handoff note exists at `.sdd/context/handoffs/latest.md`:
- Must be non-empty
- Must reference the current issue

If missing or invalid:
```
Handoff note missing or incomplete.
Write one first — include: what was done, decisions, files changed, warnings.
```

### Step 2: Verification

Run project-appropriate verification:
- If test runner exists: run tests
- If linter configured: run lint
- If build script exists: run build

If verification fails:
```
Verification failed: {details}
Fix issues and run sdd issue-complete {issue_num} again.
```

### Step 3: Knowledge Extract

Analyze the work done for reusable patterns:
1. Read debug journal if exists: `.sdd/context/sessions/issue-${issue_num}-debug.md`
2. Get changed files: `git diff HEAD~1 --name-only`
3. Extract 0-3 learnings: patterns that worked, pitfalls to avoid

If patterns found, append each to `.sdd/context/skillbook.md` using the format:

→ See context.md §Skillbook YAML Template

Only extract if the pattern would help a future agent avoid a mistake or apply a non-obvious solution. Generic observations are not worth capturing.

### Step 4: Close Issue

**If `GH_AVAILABLE=1`:**
```bash
check_remote_origin
REPO=$(get_repo)

# Post close comment if knowledge was extracted
if [ -f "/tmp/issue-close-comment-${issue_num}.md" ]; then
  gh issue comment $issue_num --repo "$REPO" --body-file "/tmp/issue-close-comment-${issue_num}.md"
  rm -f "/tmp/issue-close-comment-${issue_num}.md"
fi

gh issue close $issue_num --repo "$REPO"
```

**If `GH_AVAILABLE=0` (sandbox fallback):**

Find local task file in `.sdd/epics/` or `.sdd/epics/standalone/`. Update frontmatter: `status: closed`, `updated: {datetime}`. Log pending close via `gh_or_local issue close`. Update epic progress if task belongs to an epic.

### Step 5: Archive Debug Journal

```bash
if [ -f ".sdd/context/sessions/issue-${issue_num}-debug.md" ]; then
  mkdir -p .sdd/context/sessions/archive
  mv ".sdd/context/sessions/issue-${issue_num}-debug.md" \
     ".sdd/context/sessions/archive/issue-${issue_num}-debug.md"
fi
```

### Step 6: Clean Up

Reset verification state:
```bash
echo '{"active_task": null}' > .sdd/context/verify/state.json 2>/dev/null || true
```

### Output

```
Issue #{issue_num} completed!
  Handoff:      Validated
  Verification: Passed (or Skipped)
  Knowledge:    Extracted (or Skipped)
  Journal:      Archived (or No journal)
  Issue:        Closed

Next:
  More issues: sdd issue-start {next_issue}
  All done:    sdd epic-verify {epic_name}
  Standalone:  Done! Clear context.
```

---

→ See conventions.md §Sandbox
