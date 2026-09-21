#!/usr/bin/env bash
# SDD Pre-Tool-Use Guard Hook (Tier 2)
#
# Hard enforcement for Claude Code. Blocks unauthorized operations:
#   1. gh issue close without verification PASS
#   2. git merge to main without verification PASS
#   3. Task completion without handoff notes
#
# Claude Code PreToolUse hook API:
#   - Receives JSON on stdin: {"tool_name": "...", "tool_input": {...}}
#   - Exit 0 = allow tool call
#   - Exit 2 = block tool call
#
# PERFORMANCE: Runs on every tool call. Fast path exits immediately
# for non-SDD operations.

set -uo pipefail

SDD_ROOT="${SDD_ROOT:-.sdd}"
VERIFY_STATE="$SDD_ROOT/context/verify/epic-state.json"

# --- Read stdin once ---

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

# --- Fast path: only check Bash tool calls ---
# gh and git commands come through the Bash tool

if [ "$tool_name" != "Bash" ]; then
  exit 0
fi

# --- Fast path: skip if command is not SDD-relevant ---

is_issue_close=false
is_merge=false
is_task_complete=false

if echo "$tool_command" | grep -qE 'gh\s+issue\s+close|gh\s+issue\s+edit\s+.*--state\s+closed'; then
  is_issue_close=true
elif echo "$tool_command" | grep -qE 'git\s+merge\s+.*(main|master)'; then
  is_merge=true
elif echo "$tool_command" | grep -qE 'gh\s+issue\s+close.*epic|issue-complete|epic-merge|epic-close'; then
  is_task_complete=true
fi

# Not SDD-relevant — allow immediately
if ! $is_issue_close && ! $is_merge && ! $is_task_complete; then
  exit 0
fi

# --- Helper: check verify state ---

check_verify_pass() {
  if [ ! -f "$VERIFY_STATE" ]; then
    echo "" >&2
    echo "❌ No verification state: Run epic-verify first" >&2
    echo "" >&2
    exit 2
  fi

  local overall=""
  if command -v jq &>/dev/null; then
    overall=$(jq -r '.overall // empty' "$VERIFY_STATE" 2>/dev/null)
  elif command -v python3 &>/dev/null; then
    overall=$(python3 -c "
import json
with open('$VERIFY_STATE') as f:
    d = json.load(f)
print(d.get('overall', ''))
" 2>/dev/null)
  else
    # Fallback: grep for overall field
    overall=$(grep -o '"overall"[[:space:]]*:[[:space:]]*"[^"]*"' "$VERIFY_STATE" 2>/dev/null \
      | sed 's/.*"overall"[[:space:]]*:[[:space:]]*"//; s/".*//')
  fi

  if [ -z "$overall" ]; then
    echo "" >&2
    echo "❌ Corrupt verification state: Re-run epic-verify" >&2
    echo "" >&2
    exit 2
  fi

  if [ "$overall" != "PASS" ]; then
    echo "" >&2
    echo "❌ Verification not passed (status: $overall): Run epic-verify before this operation" >&2
    echo "" >&2
    exit 2
  fi
}

# --- Guard 1: Issue close without verification ---

if $is_issue_close; then
  check_verify_pass
fi

# --- Guard 2: Merge to main without verification ---

if $is_merge; then
  check_verify_pass
fi

# --- Guard 3: Task completion without handoff ---

if $is_task_complete; then
  HANDOFF="$SDD_ROOT/context/handoffs/latest.md"
  if [ ! -f "$HANDOFF" ]; then
    echo "" >&2
    echo "❌ No handoff notes: Write handoff before completing task" >&2
    echo "" >&2
    exit 2
  fi
fi

# --- All checks passed ---

exit 0
