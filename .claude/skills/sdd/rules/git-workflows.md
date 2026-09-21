# Git Workflows

## Branch Workflow

Create branches from a clean main branch:
```bash
git checkout main && git pull origin main
git checkout -b epic/{name}
git push -u origin epic/{name}
```

### Merging Branch to Main
```bash
git checkout main && git pull origin main
git merge epic/{name}
git branch -d epic/{name}
git push origin --delete epic/{name}
```

### Branch Management
```bash
git branch -a                              # List branches
git branch -v                              # Branch info
git log --oneline main..epic/{name}        # Compare with main
git branch -D epic/{name}                  # Force delete local
git push origin --delete epic/{name}       # Delete remote
```

## Worktree Workflow

Create worktrees as sibling directories:
```bash
git checkout main && git pull origin main
git worktree add ../epic-{name} -b epic/{name}
```

Work in the worktree: `cd ../epic-{name}`

### Merging Worktree to Main
```bash
cd {main-repo}
git checkout main && git pull origin main
git merge epic/{name}
git worktree remove ../epic-{name}
git branch -d epic/{name}
```

### Worktree Management
```bash
git worktree list                                # List worktrees
git worktree prune                               # Clean stale refs
git worktree remove --force ../epic-{name}       # Force remove
```

## Common Rules (Both Workflows)

### Agent Commits
- Commit directly to epic branch
- Small, focused commits: `Issue #{number}: {description}`

### Parallel Work
Multiple agents can work on same branch/worktree if touching different files. Coordinate on shared files — pull before modifying.

### Handling Conflicts
```bash
git status                    # See conflicts
# Human resolves conflicts
git add {resolved-files}
git commit
```

### Best Practices
1. **One branch/worktree per epic** — not per issue
2. **Clean before create** — always start from updated main
3. **Commit frequently** — smaller commits = fewer conflicts
4. **Pull before push** — stay synchronized
5. **Clean up after merge** — delete branches and worktrees
