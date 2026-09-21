# Epic Merge

Merge a completed epic branch to main, clean up branches, close issues, update status.

## epic-merge

### Pre-Merge Gate

> **STOP: Do NOT merge without verification PASS in `.sdd/context/verify/epic-state.json`.**

```bash
EPIC_NAME="{epic}"
STATE_FILE=".sdd/context/verify/epic-state.json"
PROGRESS_FILE=".sdd/epics/$EPIC_NAME/progress.md"

if [ ! -f "$STATE_FILE" ]; then
  echo "No verification state found. Run epic-verify first."
  exit 1
fi

OVERALL=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('overall','NONE'))" 2>/dev/null || echo "NONE")
if [ "$OVERALL" != "PASS" ]; then
  echo "Verification status: $OVERALL. Cannot merge."
  echo "Run epic-verify $EPIC_NAME to pass verification."
  exit 1
fi

# Completion-% gate via helper. Helper auto-falls-back to grep if python3 missing;
# fallback validates completion-% key only — malformed JSON the python path would
# reject MAY pass the grep gate. See `scripts/pm/json-or-grep.sh` header (R-5 / FR-5).
# Invoked via repo-relative absolute path (F-10 prevention — no bare `json-or-grep.sh`).
if [ -f "$PROGRESS_FILE" ]; then
  bash scripts/pm/json-or-grep.sh "$PROGRESS_FILE" 100 || {
    echo "Completion gate failed (progress < 100%). Cannot merge."
    exit 1
  }
fi
```

### Pre-Merge Validation

1. Check for uncommitted changes:
   ```bash
   if [ -n "$(git status --porcelain)" ]; then
     echo "Uncommitted changes detected. Commit or stash before merging."
     git status --short
     exit 1
   fi
   ```

2. Verify all tasks are closed:
   ```bash
   for task_file in .sdd/epics/$EPIC_NAME/[0-9]*.md; do
     [ -f "$task_file" ] || continue
     status=$(grep '^status:' "$task_file" | head -1 | sed 's/^status: *//')
     if [ "$status" != "closed" ]; then
       echo "Open task: $(basename "$task_file") — status: $status"
       echo "Cannot merge with open tasks."
       exit 1
     fi
   done
   ```

### Update Epic Status

```bash
CURRENT_DT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

Update `.sdd/epics/$EPIC_NAME/epic.md` frontmatter:
- `status: completed`
- `progress: 100%`
- `completed: {CURRENT_DT}`
- `updated: {CURRENT_DT}`

### Merge Flow

Follow conventions.md git merge pattern:

```bash
git checkout main && git pull origin main
git merge epic/$EPIC_NAME --no-ff -m "Merge epic: $EPIC_NAME"
```

**If merge conflicts occur:**
- Present the list of conflicting files to the user
- Do NOT auto-resolve conflicts
- Offer options: resolve manually, or abort with `git merge --abort`
- Preserve the epic branch for retry

After successful merge:
```bash
git push origin main
```

### Branch Cleanup

```bash
# Delete local branch
git branch -d epic/$EPIC_NAME

# Delete remote branch (if available)
source skill/sdd/scripts/gh-helper.sh
if [ "$GH_AVAILABLE" -eq 1 ]; then
  git push origin --delete epic/$EPIC_NAME 2>/dev/null || true
fi
```

If using worktree:
```bash
git worktree remove ../epic-$EPIC_NAME 2>/dev/null || true
```

### Archive Epic

```bash
mkdir -p .sdd/epics/.archived/
mv .sdd/epics/$EPIC_NAME .sdd/epics/.archived/
```

### Close GitHub Issues

```bash
source skill/sdd/scripts/gh-helper.sh
check_remote_origin || exit 1
REPO=$(get_repo)
```

Close epic issue:
```bash
epic_github=$(grep '^github:' .sdd/epics/.archived/$EPIC_NAME/epic.md 2>/dev/null | head -1 | sed 's/^github: *//')
if [ -n "$epic_github" ]; then
  epic_issue=$(echo "$epic_github" | grep -oE '[0-9]+$')
  gh_or_local issue close "$epic_issue" --repo "$REPO" -c "Epic completed and merged to main"
fi
```

Close task issues:
```bash
for task_file in .sdd/epics/.archived/$EPIC_NAME/[0-9]*.md; do
  [ -f "$task_file" ] || continue
  task_github=$(grep '^github:' "$task_file" 2>/dev/null | head -1 | sed 's/^github: *//')
  if [ -n "$task_github" ]; then
    issue_num=$(echo "$task_github" | grep -oE '[0-9]+$')
    [ -n "$issue_num" ] && gh_or_local issue close "$issue_num" --repo "$REPO" -c "Completed in epic merge"
  fi
done
```

### Update PRD Status

If the epic references a PRD (`prd:` field in epic frontmatter):
- Update PRD frontmatter: `status: complete`, `updated: {CURRENT_DT}`

→ See conventions.md §Sandbox

### Output

```
Epic merged: $EPIC_NAME

  Branch: epic/$EPIC_NAME -> main
  Commits merged: {count}
  Files changed: {count}
  Issues closed: {count}

Cleanup:
  - Tasks verified closed
  - Epic status: completed (100%)
  - Branch deleted (local + remote)
  - Epic archived
  - GitHub issues closed

Next: Start new epic or view history with git log --oneline -20
```
