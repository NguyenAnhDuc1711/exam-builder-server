#!/usr/bin/env bash
# SDD Pre-Task Hook: Context Loading & Rotation
#
# Triggered at the start of every SDD task (via /pm:issue-start).
# Responsibilities:
#   1. Check for previous context (handoff notes)
#   2. Rotate old handoff notes (keep max 10)
#   3. Output context loading protocol for Claude to follow
#
# Usage:
#   bash hooks/pre-task.sh [sdd_root]
#
# Exit codes:
#   0 = success (always — pre-task should never block)

set -uo pipefail

SDD_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HANDOFFS_DIR="$SDD_ROOT/context/handoffs"
ARCHIVE_DIR="$HANDOFFS_DIR/.archive"
MAX_HANDOFFS=10

# Source lifecycle helpers if available
HELPERS="$SDD_ROOT/scripts/pm/lifecycle-helpers.sh"
if [ -f "$HELPERS" ]; then
  source "$HELPERS" 2>/dev/null || true
fi

# --- Step 1: Check for previous context ---

has_latest=false
if [ -f "$HANDOFFS_DIR/latest.md" ]; then
  has_latest=true
else
  echo "⚠️ No previous context found ($HANDOFFS_DIR/latest.md missing). Starting fresh."
fi

# --- Step 2: Rotate old handoff notes ---

mkdir -p "$ARCHIVE_DIR" 2>/dev/null || true

# Count handoff files (task-*.md pattern)
handoff_count=$(find "$HANDOFFS_DIR" -maxdepth 1 -name "task-*.md" -type f 2>/dev/null | wc -l | tr -d ' ')

if [ "$handoff_count" -gt "$MAX_HANDOFFS" ]; then
  # Move oldest files to archive (keep newest MAX_HANDOFFS)
  archived=0
  for f in $(ls -t "$HANDOFFS_DIR"/task-*.md 2>/dev/null | tail -n +"$((MAX_HANDOFFS + 1))"); do
    mv "$f" "$ARCHIVE_DIR/" 2>/dev/null && archived=$((archived + 1))
  done
  if [ "$archived" -gt 0 ]; then
    echo "📦 Archived $archived old handoff notes (kept newest $MAX_HANDOFFS)"
  fi
fi

# --- Step 3: Output context loading protocol ---

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  CONTEXT LOADING PROTOCOL"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Before writing any code, you MUST:"
echo ""

if [ "$has_latest" = true ]; then
  echo "  1. Read $HANDOFFS_DIR/latest.md"
  echo "  2. Read the epic context file for the current epic (if exists)"
  echo "  3. Summarize: 'I understand that...' with key points"
  echo "  4. List files you plan to modify"
  echo "  5. Wait for human confirmation before proceeding"
else
  echo "  1. No previous handoff found — this appears to be a fresh start"
  echo "  2. Read the epic context file for the current epic (if exists)"
  echo "  3. Review the task description and acceptance criteria"
  echo "  4. List files you plan to create or modify"
  echo "  5. Wait for human confirmation before proceeding"
fi

echo ""
echo "DO NOT skip this protocol. DO NOT start coding immediately."
echo "═══════════════════════════════════════════════════════"
echo ""

# --- Step 3.5: Design History (Memory Agent) ---
# Runs before Design Gate — inject past patterns for FEATURE/REFACTOR/ENHANCEMENT tasks.
# Skipped if: _design_gate_skip=true (set below), memory_agent disabled, or agent unavailable.
# We need task type now, so read verify state early for the skip check.
_pretask_state_file="$SDD_ROOT/context/verify/state.json"
_pretask_task_type=""
if [ -f "$_pretask_state_file" ]; then
  _pretask_task_type=$(_json_get "$_pretask_state_file" '.active_task.type' 2>/dev/null || echo "")
fi

_run_design_history=false
case "$_pretask_task_type" in
  FEATURE|REFACTOR|ENHANCEMENT)
    if read_config_bool "memory_agent" "enabled" "false" 2>/dev/null && \
       read_config_bool "memory_agent" "query_on_pretask" "false" 2>/dev/null; then
      _run_design_history=true
    fi
    ;;
esac

if [ "$_run_design_history" = true ]; then
  _pretask_issue_num=$(_json_get "$_pretask_state_file" '.active_task.issue_number' 2>/dev/null || echo "")

  # Build query title from issue
  _query_title=""
  if [ -n "$_pretask_issue_num" ]; then
    _pretask_repo_flag=""
    _pretask_gh_helpers="$SDD_ROOT/scripts/pm/github-helpers.sh"
    if [ -f "$_pretask_gh_helpers" ]; then
      _pretask_repo=$(bash "$_pretask_gh_helpers" get-repo-for-issue "$_pretask_issue_num" 2>/dev/null || echo "")
      [ -n "$_pretask_repo" ] && _pretask_repo_flag="--repo $_pretask_repo"
    fi
    _query_title=$(gh issue view "$_pretask_issue_num" $_pretask_repo_flag --json title -q .title 2>/dev/null || echo "")
  fi
  [ -z "$_query_title" ] && _query_title="task design patterns"

  _history=$(memory_query "previous implementations patterns decisions for: ${_query_title}" "markdown" "10" 2>/dev/null || echo "")

  echo "═══════════════════════════════════════════════════════"
  echo "  DESIGN HISTORY"
  echo "═══════════════════════════════════════════════════════"
  echo ""
  if [ -n "$_history" ] && [ "$_history" != "null" ]; then
    echo "$_history"
  else
    echo "  No related patterns found. Designing from scratch."
  fi
  echo ""
fi

# --- Step 4: Design Gate Protocol ---

_design_gate_skip=true
_state_file="$SDD_ROOT/context/verify/state.json"

if [ -f "$_state_file" ] && read_config_bool "design_gate" "enabled" "true" 2>/dev/null; then
  # Read task type from verify state
  _task_type=$(_json_get "$_state_file" '.active_task.type' 2>/dev/null || echo "")
  _epic_name=$(_json_get "$_state_file" '.active_task.epic' 2>/dev/null || echo "")
  _issue_num=$(_json_get "$_state_file" '.active_task.issue_number' 2>/dev/null || echo "")

  case "$_task_type" in
    FEATURE|REFACTOR|ENHANCEMENT)
      _design_gate_skip=false
      ;;
  esac
fi

if [ "$_design_gate_skip" = false ]; then
  # Check for design spec in task frontmatter
  _design_spec=""
  _task_file=""
  if [ -n "$_epic_name" ] && [ -n "$_issue_num" ]; then
    _task_file="$SDD_ROOT/epics/${_epic_name}/${_issue_num}.md"
    if [ -f "$_task_file" ]; then
      _design_spec=$(grep '^design_spec:' "$_task_file" 2>/dev/null | sed 's/^design_spec: *//' | tr -d '"' || echo "")
    fi
  fi

  echo "═══════════════════════════════════════════════════════"
  echo "  DESIGN GATE PROTOCOL"
  echo "═══════════════════════════════════════════════════════"
  echo ""

  if [ -n "$_design_spec" ] && [ -f "$_design_spec" ]; then
    # Design spec exists — reference it instead of asking to create design file
    echo "DESIGN REFERENCE AVAILABLE:"
    echo ""
    echo "  Read design spec at: $_design_spec"
    echo "  The spec contains component tree, spacing tokens, color usage, and responsive breakpoints."
    echo "  Reference the design system at: $(dirname "$(dirname "$_design_spec")")/design-system.md"
    echo "  Use these as your implementation guide — do NOT invent new visual patterns."
  else
    # Original behavior — ask to create design file
    echo "Before writing ANY code, create a design file:"
    echo ""
    echo "  $SDD_ROOT/epics/${_epic_name}/designs/task-${_issue_num}-design.md"
    echo ""
    echo "With sections:"
    echo "  ## Approach"
    echo "  [1-3 sentences: how you will implement this]"
    echo ""
    echo "  ## Key Decisions"
    echo "  - [Decision]: [Choice] because [Reason]. Rejected: [Alternatives]."
    echo ""
    echo "  ## Files to Change"
    echo "  - [path] — [what changes and why]"
    echo ""
    echo "  ## Acceptance Criteria → Test Plan"
    echo "  - AC1: [criteria] → Test: [how to verify]"
    echo ""

    if detect_superpowers 2>/dev/null; then
      echo "Use the **brainstorming** skill to explore approaches before committing to a design."
    else
      echo "Think through at least 2 alternative approaches before choosing one."
      echo "Document why you rejected the alternatives in Key Decisions."
    fi

    echo ""
    echo "DO NOT write code before creating this design file."
    echo "Wait for user confirmation of your approach."
  fi

  echo "═══════════════════════════════════════════════════════"
  echo ""
fi

# --- Step 5: IDE Switch Detection ---

_active_ide_file="$SDD_ROOT/sync/active-ide.json"
if [ -f "$_active_ide_file" ]; then
  _last_ide=$(grep -o '"last_ide"[[:space:]]*:[[:space:]]*"[^"]*"' "$_active_ide_file" 2>/dev/null \
    | sed 's/.*"last_ide"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
  if [ -n "$_last_ide" ] && [ "$_last_ide" != "claude-code" ]; then
    echo "═══════════════════════════════════════════════════════"
    echo "  IDE TRANSITION DETECTED"
    echo "═══════════════════════════════════════════════════════"
    echo ""
    echo "  Last session: $_last_ide → Now: Claude Code"
    echo ""
    echo "  Cross-IDE context may be available:"
    echo "  1. Check $HANDOFFS_DIR/latest.md"
    echo "  2. Review before starting new work"
    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo ""
  fi
fi
# active-ide.json missing → skip silently (backward compatible)

# --- Step 6: Debug journal safety net ---
SAVE_JOURNAL="$SDD_ROOT/scripts/save-debug-journal.sh"
if [ -f "$SAVE_JOURNAL" ]; then
  bash "$SAVE_JOURNAL" 2>/dev/null || true
fi

exit 0
