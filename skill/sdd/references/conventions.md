# Conventions

Shared rules for all SDD references. Every reference doc implicitly depends on these conventions.

Cross-reference format: `→ See <file>.md §<section-name>` — used to point from a redirect stub to a canonical section elsewhere in the corpus.

## Path Convention

All SDD runtime data lives in `.sdd/` at the project root. Never write to `.claude/` during SDD operation.

### Standard Directories

```
.sdd/
  config/          # Configuration files (lifecycle.json, epic-run.json)
  context/         # Runtime context (9 project docs + subdirs below)
    epics/         # Epic context files
    handoffs/      # Handoff notes between tasks
    progress/      # Progress tracking
    sessions/      # Debug journals (local-only)
    verify/        # Verification state and reports
  epics/           # Epic definitions and task files
  prds/            # Product requirement documents
  rules/           # Project-specific rules (auto-loaded by harness)
  scripts/         # Deterministic helper scripts
```

### Path Rules

- All paths in references use `.sdd/` prefix
- User-facing output uses relative paths from project root
- Never include absolute paths (`/Users/...`, `/home/...`) in output or stored files
- Cross-project references use `../` relative paths

## Frontmatter

Canonical YAML block between `---` markers at the start of every managed file. Datetime via `date -u +"%Y-%m-%dT%H:%M:%SZ"`.

```yaml
---
name: {identifier}              # from arguments or context
status: {initial_status}        # see Status Values below
created: {ISO datetime}         # set once, never change
updated: {ISO datetime}         # refresh on any modification
---
```

**Rules:**
- **Required keys:** `name`, `status`, `created`, `updated` (plus file-specific extras). On create: set `created` and `updated` to current datetime. On update: refresh `updated` only, preserve all other fields.
- **Datetime format:** ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) from real system clock — never placeholders or estimates.
- **Strip on publish:** before sending content to GitHub (issues, comments, syncs), remove the frontmatter block: `sed '1,/^---$/d; 1,/^---$/d' input.md > output.md`.

### Status Values

| Type | Values |
|------|--------|
| PRDs | `backlog`, `in-progress`, `complete` |
| Epics | `backlog`, `in-progress`, `completed` |
| Tasks | `open`, `in-progress`, `closed` |

Progress tracking adds `progress: {0-100}%` (epics) or `completion: {0-100}%` (progress files).

## Git Workflows

### Branch Naming

One branch per epic: `epic/{name}`

```bash
# Create from clean main
git checkout main && git pull origin main
git checkout -b epic/{name}
git push -u origin epic/{name}
```

### Commit Format

Small, focused commits:

```
Issue #{number}: {description}
```

### Merging to Main

```bash
git checkout main && git pull origin main
git merge epic/{name}
git branch -d epic/{name}
git push origin --delete epic/{name}
```

### Worktree Workflow

For parallel work, create worktrees as sibling directories:

```bash
git worktree add ../epic-{name} -b epic/{name}
```

Merge:

```bash
cd {main-repo}
git checkout main && git pull origin main
git merge epic/{name}
git worktree remove ../epic-{name}
git branch -d epic/{name}
```

### Best Practices

1. One branch/worktree per epic — not per issue
2. Clean before create — always start from updated main
3. Commit frequently — smaller commits = fewer conflicts
4. Pull before push — stay synchronized
5. Clean up after merge — delete branches and worktrees

## GitHub Operations

### Repository Protection

Before ANY write operation (create/edit issues, PRs, comments), check remote origin:

```bash
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$remote_url" == *"automazeio/ccpm"* ]]; then
  echo "❌ Cannot modify template repo. Run: git remote set-url origin YOUR_REPO_URL"
  exit 1
fi
```

### Derive Repo

```bash
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
REPO=$(echo "$remote_url" | sed 's|.*github.com[:/]||' | sed 's|\.git$||')
[ -z "$REPO" ] && REPO="user/repo"
```

### Authentication

Don't pre-check. Run the command and handle failure:

```bash
gh {command} || echo "❌ GitHub CLI failed. Run: gh auth login"
```

### Common Operations

```bash
# View issue
gh issue view {number} --json state,title,labels,body

# Create issue (always specify repo)
gh issue create --repo "$REPO" --title "{title}" --body-file {file} --label "{labels}"

# Update issue
gh issue edit {number} --add-label "{label}" --add-assignee @me

# Comment on issue
gh issue comment {number} --body-file {file}
```

### Error Handling

If any `gh` command fails:
1. Show: `❌ GitHub operation failed: {command}`
2. Suggest fix: `Run: gh auth login` or check issue number
3. Don't retry automatically

## Error Messages

### Format

Short and actionable:

```
❌ {What failed}: {Exact solution}
```

Examples:
- `❌ Epic not found: Run sdd prd-parse feature-name`
- `❌ GitHub CLI failed: Run gh auth login`

### Status Indicators

- ✅ Success (use sparingly)
- ❌ Error (always with solution)
- ⚠️ Warning (only if action needed)

## Standard Output

### Success

```
✅ {Action} complete
  - {Key result 1}
  - {Key result 2}
Next: {Single suggested action}
```

### Lists

```
{Count} {items} found:
- {item 1}: {key detail}
- {item 2}: {key detail}
```

### Progress

```
{Action}... {current}/{total}
```

## Core Principles

1. **Fail Fast** — check critical prerequisites, then proceed
2. **Trust the System** — don't over-validate things that rarely fail
3. **Clear Errors** — say exactly what failed and how to fix it
4. **Minimal Output** — show what matters, skip decoration
5. **Smart Defaults** — proceed with sensible defaults; only ask when destructive or ambiguous

## File Operations

```bash
# Create directories without asking
mkdir -p .sdd/{directory} 2>/dev/null

# Read with fallback
if [ -f {file} ]; then
  # Read and use file
else
  # Use sensible default
fi
```

## Normalize Paths

Strip absolute paths before publishing:

```bash
normalize_paths() {
  local content="$1"
  content=$(echo "$content" | sed "s|/Users/[^/]*/[^/]*/|../|g")
  content=$(echo "$content" | sed "s|/home/[^/]*/[^/]*/|../|g")
  echo "$content"
}
```

## Sandbox

Canonical home for sandbox-mode (`gh`-unavailable) behaviour. Every command that touches GitHub MUST source `skill/sdd/scripts/gh-helper.sh` and respect this fallback.

```bash
source skill/sdd/scripts/gh-helper.sh
```

**Modes:**
- `GH_AVAILABLE=1` — normal `gh` CLI operations.
- `GH_AVAILABLE=0` — files created locally; every GitHub operation is logged to `.sdd/context/pending-sync.md` for later replay.

**Helpers (drop-in primitives, see `skill/sdd/scripts/gh-helper.sh`):**
- `gh_or_local()` — drop-in replacement for `gh`; works in both modes (executes `gh` when available, logs to `pending-sync.md` otherwise).
- `check_remote_origin` — blocks writes to the upstream template repo (`automazeio/ccpm`) before any create/edit; exits non-zero on match.
- `get_repo` — derives `OWNER/REPO` from `git remote get-url origin`; falls back to `user/repo` if unset.
- `strip_frontmatter` — removes YAML frontmatter from a file before sending the body to GitHub.

**Per-command behaviour when `GH_AVAILABLE=0`:**
- `epic-start` — skip `git push -u origin`; work locally only.
- `epic-run` — skip GitHub issue close; update local task status; log close to pending-sync.
- `epic-merge` — skip GitHub issue closing; all local operations (merge, branch delete, archive, status update) proceed normally; log pending ops via `gh_or_local`.
- `issue-new` — create `.sdd/epics/standalone/issue-{N}.md` instead of `gh issue create`.
- `issue-start` — read local task file and update frontmatter instead of `gh issue view/edit`.
- `issue-complete` — update local status to `closed` instead of `gh issue close`.

**Pending-sync flow:** when `gh` becomes available again, replay the queued `gh` commands from `.sdd/context/pending-sync.md`. The full pipeline (PRD, epic, tasks, branch, local files) completes regardless of `gh` availability — only GitHub-issue sync is deferred.

Output on degradation: `GitHub operations logged for later sync. Run gh auth login when available.`

## AskUserQuestion Decision-Brief Format

Every `AskUserQuestion` emitted by a SDD skill MUST include all 6 fields below. Each decision gets a sequential `D-N` number within the session.

| Field | Constraint |
|-------|-----------|
| D-N | Sequential label: `D-1`, `D-2`, … |
| ELI10 | 1 line, plain language, no jargon |
| Recommendation | 1 line: default option + reason |
| Pros | Bullet list per option; each bullet ≥40 chars |
| Cons | Bullet list per option; each bullet ≥40 chars |
| Net | 1 line: "Pick X because Y" |

**Worked example — AD-1 single-provider choice:**

```
D-1
ELI10: Should plan-review use two different AI models or just Claude?
Recommendation: Claude-only (sonnet+opus) — zero new auth, ships today.
Pros:
  - Claude-only: no Codex setup, single billing surface, ships FR-14 now
  - Codex+Claude: cross-vendor architectural diversity in findings
Cons:
  - Claude-only: sonnet/opus may converge faster than cross-vendor pair
  - Codex+Claude: breaks C-1 (single-provider), adds OpenAI auth burden
Net: Pick Claude-only because zero-friction adoption outweighs diversity risk (SC-4 monitors convergence).
```

Enforced by `scripts/pm/conventions-lint.sh` (see T020); breach is a critical finding in plan-review.

### Plain-text fallback (when AskUserQuestion cannot render)

Use when the interactive `AskUserQuestion` tool fails or is unavailable (non-interactive shell, headless CI). Render the same 6-field Decision-Brief as plain text — the brief content is identical; only the presentation changes.

**Format:**

```
[AskUserQuestion fallback — tool unavailable]
Completeness: N/6 fields known  (count the 6 fields that are populated)

D-N
ELI10:          <value>
Recommendation: <value>
Pros:
  - <option>: <bullet ≥40 chars>
  ...
Cons:
  - <option>: <bullet ≥40 chars>
  ...
Net: <value>

Reply with a single letter:
  A) <option A label>
  B) <option B label>
  C) <option C label / "Continue / proceed">
```

**Rules:**
- `Completeness: N/6` counts how many of the 6 fields (D-N, ELI10, Recommendation, Pros, Cons, Net) are populated; a fully-known brief scores 6/6.
- The user answers by typing one letter (A, B, C, …). No other input is required.
- This is a **degradation path only** — when the tool renders normally, the existing interactive brief is unaffected (additive, non-breaking).
- Applied at exactly 3 call-sites: `plan-review` (in `plan-review.md`), `office-hours` (in `plan.md`), and `prd-rethink` (also in `plan.md`). It is defined once here (AD-8 / DRY) and referenced at each site.
