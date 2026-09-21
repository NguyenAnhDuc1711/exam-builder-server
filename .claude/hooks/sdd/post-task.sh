#!/usr/bin/env bash
# SDD Post-Task Hook: Handoff Validation & Context Commit
#
# Triggered at task completion (via /pm:issue-complete).
# Responsibilities:
#   1. Validate handoff note exists and is fresh
#   2. Validate required sections in handoff note
#   3. Warn about missing architecture decisions
#   4. Stage and commit context files
#
# Usage:
#   bash hooks/post-task.sh [sdd_root]
#
# Exit codes:
#   0 = all checks passed
#   1 = hard failure (handoff missing or stale) — blocks completion

set -uo pipefail

SDD_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HANDOFFS_DIR="$SDD_ROOT/context/handoffs"
LATEST="$HANDOFFS_DIR/latest.md"
ARCH_DECISIONS="$SDD_ROOT/context/architecture-decisions.md"
FAIL=0
WARNINGS=0

# Source lifecycle helpers if available
HELPERS="$SDD_ROOT/scripts/pm/lifecycle-helpers.sh"
if [ -f "$HELPERS" ]; then
  source "$HELPERS" 2>/dev/null || true
fi

echo "═══ SDD Post-Task: Handoff Validation ═══"
echo ""

# --- Step 1: Check handoff note exists ---

echo "── Step 1: Handoff Note Exists ──"
if [ ! -f "$LATEST" ]; then
  echo "❌ Handoff note missing: $LATEST"
  echo "   Write a handoff note before completing this task."
  echo "   Template: $HANDOFFS_DIR/TEMPLATE.md"
  FAIL=1
else
  echo "✅ Handoff note found"
fi

# --- Step 2: Check handoff freshness (modified within last 10 minutes) ---

echo ""
echo "── Step 2: Handoff Freshness ──"
if [ "$FAIL" -eq 0 ]; then
  fresh=$(find "$LATEST" -mmin -10 -print 2>/dev/null)
  if [ -z "$fresh" ]; then
    echo "❌ Handoff note is stale (not modified in last 10 minutes)"
    echo "   Update $LATEST with current task results."
    FAIL=1
  else
    echo "✅ Handoff note is fresh (modified within last 10 minutes)"
  fi
fi

# --- Step 3: Validate required sections ---

echo ""
echo "── Step 3: Required Sections ──"
if [ "$FAIL" -eq 0 ]; then
  required_sections=("## Completed" "## Decisions Made" "## State of Tests" "## Files Changed")
  all_found=true

  for section in "${required_sections[@]}"; do
    if grep -q "^${section}" "$LATEST" 2>/dev/null; then
      echo "  ✅ $section"
    else
      echo "  ❌ $section — missing"
      all_found=false
      FAIL=1
    fi
  done

  # Soft checks (warn but don't block)
  optional_sections=("## Decisions Made" "## Interfaces Exposed/Modified" "## Warnings for Next Task")
  for section in "${optional_sections[@]}"; do
    if grep -q "^${section}" "$LATEST" 2>/dev/null; then
      # Check section has content (not just the header)
      section_line=$(grep -n "^${section}" "$LATEST" | head -1 | cut -d: -f1)
      next_section_line=$(awk -v start="$((section_line + 1))" 'NR > start && /^## /{print NR; exit}' "$LATEST" 2>/dev/null)
      if [ -z "$next_section_line" ]; then
        next_section_line=$(wc -l < "$LATEST" | tr -d ' ')
      fi
      content_lines=$((next_section_line - section_line - 1))
      if [ "$content_lines" -le 1 ]; then
        echo "  ⚠️ $section — empty (consider adding content)"
        WARNINGS=$((WARNINGS + 1))
      fi
    fi
  done

  # --- Design traceability check (Superpowers Integration) ---
  _design_file=""
  _state_file="$SDD_ROOT/context/verify/state.json"
  if [ -f "$_state_file" ]; then
    _dt_epic=""
    _dt_issue=""
    if command -v jq &>/dev/null; then
      _dt_epic=$(jq -r '.active_task.epic // empty' "$_state_file" 2>/dev/null)
      _dt_issue=$(jq -r '.active_task.issue_number // empty' "$_state_file" 2>/dev/null)
    else
      _dt_epic=$(python3 -c "
import json
with open('$_state_file') as f:
    d = json.load(f)
print(d.get('active_task', {}).get('epic', ''))
" 2>/dev/null)
      _dt_issue=$(python3 -c "
import json
with open('$_state_file') as f:
    d = json.load(f)
print(d.get('active_task', {}).get('issue_number', ''))
" 2>/dev/null)
    fi
    if [ -n "$_dt_epic" ] && [ -n "$_dt_issue" ]; then
      _design_file="$SDD_ROOT/epics/${_dt_epic}/designs/task-${_dt_issue}-design.md"
    fi
  fi

  if [ -n "$_design_file" ] && [ -f "$_design_file" ]; then
    if ! grep -q "^## Design vs Implementation" "$LATEST" 2>/dev/null; then
      echo "  ⚠️ ## Design vs Implementation — missing (design file exists, trace your decisions)"
      WARNINGS=$((WARNINGS + 1))
    fi
  fi
fi

# --- Step 4: Architecture decisions check ---

echo ""
echo "── Step 4: Architecture Decisions ──"
# Check if there are new files in git diff AND architecture-decisions.md is unchanged
new_files=$(git diff --cached --name-only --diff-filter=A 2>/dev/null | wc -l | tr -d ' ')
arch_changed=false
if [ -f "$ARCH_DECISIONS" ]; then
  git diff --cached --name-only 2>/dev/null | grep -q "architecture-decisions" && arch_changed=true
fi

if [ "$new_files" -gt 3 ] && [ "$arch_changed" = false ]; then
  echo "⚠️ $new_files new files added but architecture-decisions.md not updated"
  echo "   Consider documenting significant architectural choices."
  WARNINGS=$((WARNINGS + 1))
else
  echo "✅ Architecture decisions check passed"
fi

# --- Step 5: Stage and commit context files ---

echo ""
echo "── Step 5: Context Commit ──"
if [ "$FAIL" -eq 0 ]; then
  # Only commit if there are context changes
  context_changes=$(git status --porcelain "$SDD_ROOT/context/" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$context_changes" -gt 0 ]; then
    git add "$SDD_ROOT/context/" 2>/dev/null
    git commit -m "[Context] Task handoff" 2>/dev/null && \
      echo "✅ Context files committed" || \
      echo "⚠️ Context commit skipped (nothing to commit or commit failed)"
  else
    echo "✅ No context changes to commit"
  fi
else
  echo "⏭️ Skipped (handoff validation failed)"
fi

# --- Summary ---

echo ""
echo "═══════════════════════════════"
if [ "$FAIL" -ne 0 ]; then
  echo "❌ BLOCKED: Fix the issues above before completing this task."
  echo ""
  echo "Quick fix:"
  echo "  1. Copy template: cp \"$HANDOFFS_DIR/TEMPLATE.md\" \"$LATEST\""
  echo "  2. Fill in all required sections"
  echo "  3. Try completing again"
  exit 1
fi

if [ "$WARNINGS" -gt 0 ]; then
  echo "✅ PASSED with $WARNINGS warning(s)"
else
  echo "✅ PASSED — all checks clean"
fi

exit 0
