#!/usr/bin/env bash
# SDD Pre-Tool-Use Guard Hook
#
# Monitors every tool call for dangerous patterns:
#   1. Closing a GitHub issue without verification passing
#   2. Committing code without a fresh handoff note
#
# Claude Code PreToolUse hook API:
#   - Receives JSON on stdin: {"tool_name": "...", "tool_input": {...}}
#   - Exit 0 = allow tool call
#   - Exit 2 = block tool call
#
# Usage:
#   echo '{"tool_name":"Bash","tool_input":{"command":"gh issue close 12"}}' | bash hooks/pre-tool-use.sh [sdd_root]
#
# PERFORMANCE: This runs on every tool call. Keep it fast.
#   - Read stdin once, parse minimally
#   - Only source helpers when active task detected
#   - Skip checks entirely when no active task

set -uo pipefail

SDD_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STATE_FILE="$SDD_ROOT/context/verify/state.json"

# --- Fast path: no state file or no active task = allow everything ---

if [ ! -f "$STATE_FILE" ]; then
  exit 0
fi

# Quick check for active task without sourcing helpers (performance)
if command -v jq &>/dev/null; then
  active=$(jq -r '.active_task // empty' "$STATE_FILE" 2>/dev/null)
else
  active=$(python3 -c "
import json
with open('$STATE_FILE') as f:
    d = json.load(f)
print(d.get('active_task') or '')
" 2>/dev/null)
fi

if [ -z "$active" ] || [ "$active" = "null" ]; then
  exit 0
fi

# --- Active task exists: read stdin and check patterns ---

input=$(cat)
tool_name=""
tool_command=""

if command -v jq &>/dev/null; then
  tool_name=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null)
  tool_command=$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  tool_name=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('tool_name', ''))
" <<< "$input" 2>/dev/null)
  tool_command=$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('tool_input', {}).get('command', ''))
" <<< "$input" 2>/dev/null)
fi

# --- Design Gate: Check Write/Edit tools ---
if [[ "$tool_name" == "Write" || "$tool_name" == "Edit" ]]; then
  # Source helpers for config reading
  HELPERS="$SDD_ROOT/scripts/pm/lifecycle-helpers.sh"
  if [ -f "$HELPERS" ]; then
    source "$HELPERS" 2>/dev/null || true
  fi

  # Check if design gate is enabled
  if read_config_bool "design_gate" "enabled" "true" 2>/dev/null; then
    # Read task type from state
    task_type=""
    if command -v jq &>/dev/null; then
      task_type=$(jq -r '.active_task.type // empty' "$STATE_FILE" 2>/dev/null)
    else
      task_type=$(python3 -c "
import json
with open('$STATE_FILE') as f:
    d = json.load(f)
print(d.get('active_task', {}).get('type', ''))
" 2>/dev/null)
    fi

    # Only check FEATURE/REFACTOR/ENHANCEMENT
    if [[ "$task_type" =~ ^(FEATURE|REFACTOR|ENHANCEMENT)$ ]]; then
      # Get file_path from tool input
      file_path=""
      if command -v jq &>/dev/null; then
        file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
      else
        file_path=$(python3 -c "
import json, sys
d = json.loads('''$input''')
print(d.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null)
      fi

      # Allow if writing design file itself
      if [[ "$file_path" == *"designs/task-"* ]]; then
        exit 0
      fi

      # Check if design file exists
      epic_name=""
      issue_num=""
      if command -v jq &>/dev/null; then
        epic_name=$(jq -r '.active_task.epic // empty' "$STATE_FILE" 2>/dev/null)
        issue_num=$(jq -r '.active_task.issue_number // empty' "$STATE_FILE" 2>/dev/null)
      else
        epic_name=$(python3 -c "
import json
with open('$STATE_FILE') as f:
    d = json.load(f)
t = d.get('active_task', {})
print(t.get('epic', ''))
" 2>/dev/null)
        issue_num=$(python3 -c "
import json
with open('$STATE_FILE') as f:
    d = json.load(f)
t = d.get('active_task', {})
print(t.get('issue_number', ''))
" 2>/dev/null)
      fi

      if [ -n "$epic_name" ] && [ -n "$issue_num" ]; then
        design_file="$SDD_ROOT/epics/${epic_name}/designs/task-${issue_num}-design.md"
        if [ ! -f "$design_file" ]; then
          echo "" >&2
          echo "❌ ═══ BLOCKED: Design file required before coding ═══" >&2
          echo "" >&2
          echo "  Task type $task_type requires a design file." >&2
          echo "  Create: $design_file" >&2
          echo "" >&2
          echo "  Include sections: Approach, Key Decisions, Files to Change, AC → Test Plan" >&2
          echo "  Then retry your edit." >&2
          echo "" >&2
          exit 2
        fi
      fi
    fi
  fi
  exit 0
fi

# Only check Bash tool calls (gh and git commands come through Bash)
if [ "$tool_name" != "Bash" ]; then
  exit 0
fi

# --- Guard 1: Issue close without verification ---

if echo "$tool_command" | grep -qE '(gh\s+issue\s+close|gh\s+issue\s+edit\s+.*--state\s+closed)'; then
  # Check if verification has passed
  last_result=""
  if command -v jq &>/dev/null; then
    last_result=$(jq -r '
      .active_task.iterations[-1].result // empty
    ' "$STATE_FILE" 2>/dev/null)
  else
    last_result=$(python3 -c "
import json
with open('$STATE_FILE') as f:
    d = json.load(f)
iters = d.get('active_task', {}).get('iterations', [])
print(iters[-1].get('result', '') if iters else '')
" 2>/dev/null)
  fi

  if [ "$last_result" != "VERIFY_PASS" ]; then
    echo "" >&2
    echo "❌ ═══ BLOCKED: Cannot close issue without passing verification ═══" >&2
    echo "" >&2
    echo "  Active task detected in verify state." >&2
    echo "  Last verification result: ${last_result:-none}" >&2
    echo "" >&2
    echo "  Run: /pm:verify-run    — to run verification" >&2
    echo "  Run: /pm:verify-skip   — to bypass with reason" >&2
    echo "" >&2
    exit 2
  fi
fi

# --- Guard 2: Git commit without handoff note ---

if echo "$tool_command" | grep -qE 'git\s+commit'; then
  # Skip context commits (they're from our own hooks)
  if echo "$tool_command" | grep -q '\[Context\]'; then
    exit 0
  fi

  # Check if handoff note exists and is fresh
  latest="$SDD_ROOT/context/handoffs/latest.md"
  if [ -f "$latest" ]; then
    fresh=$(find "$latest" -mmin -10 -print 2>/dev/null)
    if [ -z "$fresh" ]; then
      echo ""
      echo "⚠️ Handoff note not updated in last 10 minutes."
      echo "   Consider running /pm:handoff-write before completing."
      echo ""
      # Warn only, don't block commits
      exit 0
    fi
  fi
fi

# --- Allow all other tool calls ---

exit 0
