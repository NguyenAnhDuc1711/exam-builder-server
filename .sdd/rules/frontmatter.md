# Frontmatter

## DateTime

**ALWAYS** get real system time. Never use placeholders or estimates.

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

- Format: ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`)
- On create: set both `created` and `updated` to current time
- On update: update `updated` only, preserve `created`
- Applies to all frontmatter: PRDs, epics, tasks, progress, sync timestamps

## Reading & Updating

Extract frontmatter from between `---` markers at start of file. Parse as YAML; use sensible defaults if missing.

When updating:
1. Preserve all existing fields
2. Only update specified fields
3. Always update `updated` with current datetime

### Standard Fields
```yaml
---
name: {identifier}
created: {ISO datetime}      # Never change after creation
updated: {ISO datetime}      # Update on any modification
---
```

### Status Values
- PRDs: `backlog`, `in-progress`, `complete`
- Epics: `backlog`, `in-progress`, `completed`
- Tasks: `open`, `in-progress`, `closed`

### Progress Tracking
```yaml
progress: {0-100}%           # For epics
completion: {0-100}%         # For progress files
```

### Creating New Files
```yaml
---
name: {from_arguments_or_context}
status: {initial_status}
created: {current_datetime}
updated: {current_datetime}
---
```

## Stripping for External Use

Strip frontmatter before sending content to GitHub (issues, comments, syncs):

```bash
sed '1,/^---$/d; 1,/^---$/d' input.md > output.md
```

### Common Patterns
```bash
# Creating issue — strip frontmatter first
sed '1,/^---$/d; 1,/^---$/d' task.md > /tmp/clean.md
gh issue create --repo "$REPO" --body-file /tmp/clean.md

# Posting comment
sed '1,/^---$/d; 1,/^---$/d' progress.md > /tmp/comment.md
gh issue comment 123 --body-file /tmp/comment.md
```
