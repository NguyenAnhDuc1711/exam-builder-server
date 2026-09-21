#!/usr/bin/env bash
set -euo pipefail

SDD_ROOT="${SDD_ROOT:-.sdd}"

dirs=(prds epics context verify config sessions qa progress rules scripts)

mkdir -p "$SDD_ROOT"
for d in "${dirs[@]}"; do
  mkdir -p "$SDD_ROOT/$d"
  [ -f "$SDD_ROOT/$d/.gitkeep" ] || touch "$SDD_ROOT/$d/.gitkeep"
done

echo "SDD initialized at $SDD_ROOT/"
echo "  Directories: ${dirs[*]}"

# Generate CLAUDE.md if not present (idempotent — skip if file exists)
if [ ! -f "CLAUDE.md" ]; then
  cat > CLAUDE.md << 'CLAUDE_EOF'
# CLAUDE.md

> Think carefully and implement the most concise solution that changes as little code as possible.

## Project-Specific Instructions

Add your project-specific instructions here.

## Testing

Run tests before committing. Check `package.json`, `Makefile`, or `pyproject.toml` for the test command.

## Code Style

Follow existing patterns in the codebase.

## SDD Workflow

Manage features with SDD: PRD → Epic → Tasks → Issues → Execute → Verify.
Suggest next steps with `/sdd <command>` + `[tier/model]` annotation:
- `[medium/sonnet]`: issue-start, issue-complete, status, verify, edit
- `[heavy/opus]`: prd-rethink, prd-new, epic-run, merge, fix-gap

<!-- sdd:karpathy-section v1 -->
## Karpathy Coding Guidelines

Behavioral guidelines to reduce common LLM coding mistakes.
Full reference: skill `karpathy-coding` (auto-loads on implement/fix/refactor/build/create).

**1. Think Before Coding** — State assumptions explicitly. Present alternatives. Push back when warranted. Ask if unclear — don't assume.

**2. Simplicity First** — Minimum code that solves the problem. No speculative features, abstractions, or configurability. If 200 lines can be 50, rewrite.

**3. Surgical Changes** — Touch only what you must. Don't improve adjacent code, don't refactor things not broken. Every changed line must trace to the user's request.
<!-- /sdd:karpathy-section -->
CLAUDE_EOF
  echo "CLAUDE.md created with Karpathy Coding Guidelines"
fi

echo ""
echo "Next: Run office-hours or prd-rethink to start planning"
