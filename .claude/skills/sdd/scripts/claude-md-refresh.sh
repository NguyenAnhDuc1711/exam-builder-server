#!/usr/bin/env bash
# claude-md-refresh.sh — Append Karpathy coding principles section to CLAUDE.md
# Idempotent: skips if marker already present. Backup created before any change.
# Canonical: skill/sdd/scripts/claude-md-refresh.sh (scripts/pm/ is a legacy copy)
set -euo pipefail

MARKER_START="<!-- sdd:karpathy-section v1 -->"
MARKER_END="<!-- /sdd:karpathy-section -->"

PROJECT_DIR="."
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

CLAUDE_MD="$PROJECT_DIR/CLAUDE.md"

if [ ! -f "$CLAUDE_MD" ]; then
  echo "Error: CLAUDE.md not found at $CLAUDE_MD"
  echo "Run /sdd init first, then re-run /sdd claude-md-refresh."
  exit 1
fi

if grep -qF "$MARKER_START" "$CLAUDE_MD" 2>/dev/null; then
  echo "Karpathy section already present in CLAUDE.md — skipping."
  exit 0
fi

cp "$CLAUDE_MD" "${CLAUDE_MD}.bak"

cat >> "$CLAUDE_MD" <<'KARPATHY_EOF'

<!-- sdd:karpathy-section v1 -->
## Karpathy Coding Guidelines

Behavioral guidelines to reduce common LLM coding mistakes.
Full reference: skill `karpathy-coding` (auto-loads on implement/fix/refactor/build/create).

**1. Think Before Coding** — State assumptions explicitly. Present alternatives. Push back when warranted. Ask if unclear — don't assume.

**2. Simplicity First** — Minimum code that solves the problem. No speculative features, abstractions, or configurability. If 200 lines can be 50, rewrite.

**3. Surgical Changes** — Touch only what you must. Don't improve adjacent code, don't refactor things not broken. Every changed line must trace to the user's request.
<!-- /sdd:karpathy-section -->
KARPATHY_EOF

echo "Karpathy Coding Guidelines added to CLAUDE.md"
echo "Backup: ${CLAUDE_MD}.bak"
