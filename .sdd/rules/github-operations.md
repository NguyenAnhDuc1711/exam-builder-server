# GitHub Operations Rule

Standard patterns for GitHub CLI operations across all commands.

## CRITICAL: Repository Protection

**Before ANY write operation** (create/edit issues, PRs, comments), check remote origin is NOT the template repo:
```bash
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$remote_url" == *"automazeio/ccpm"* ]]; then
  echo "❌ ERROR: Cannot modify SDD template repo. Update remote: git remote set-url origin YOUR_REPO_URL"
  exit 1
fi
```

## Authentication

**Don't pre-check authentication.** Just run the command and handle failure:

```bash
gh {command} || echo "❌ GitHub CLI failed. Run: gh auth login"
```

## Common Operations

### Get Issue Details
```bash
gh issue view {number} --json state,title,labels,body
```

### Create Issue
```bash
# Always specify repo to avoid defaulting to wrong repository
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
REPO=$(echo "$remote_url" | sed 's|.*github.com[:/]||' | sed 's|\.git$||')
[ -z "$REPO" ] && REPO="user/repo"
gh issue create --repo "$REPO" --title "{title}" --body-file {file} --label "{labels}"
```

### Update Issue
```bash
# ALWAYS check remote origin first!
gh issue edit {number} --add-label "{label}" --add-assignee @me
```

### Add Comment
```bash
# ALWAYS check remote origin first!
gh issue comment {number} --body-file {file}
```

## Error Handling

If any gh command fails:
1. Show clear error: "❌ GitHub operation failed: {command}"
2. Suggest fix: "Run: gh auth login" or check issue number
3. Don't retry automatically

## Important Notes

- **ALWAYS** check remote origin before ANY write operation to GitHub
- Trust that gh CLI is installed and authenticated
- Use --json for structured output when parsing
- Keep operations atomic - one gh command per action
- Don't check rate limits preemptively
