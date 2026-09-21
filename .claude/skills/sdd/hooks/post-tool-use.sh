#!/usr/bin/env bash
# SDD Post-Tool-Use Hook (Tier 2)
#
# Updates SDD state after tool execution on Claude Code:
#   1. Logs issue state changes to progress/activity.log
#   2. Timestamps context modifications
#
# Claude Code PostToolUse hook API:
#   - Receives JSON on stdin: {"tool_name": "...", "tool_input": {...}, "tool_output": "..."}
#   - Exit 0 always (post-hooks should never block)
#
# PERFORMANCE: Runs on every tool call. Fast path exits immediately
# for non-SDD operations.

set -uo pipefail

SDD_ROOT="${SDD_ROOT:-.sdd}"
PROGRESS_DIR="$SDD_ROOT/progress"
ACTIVITY_LOG="$PROGRESS_DIR/activity.log"
CONTEXT_TS="$SDD_ROOT/context/last-modified"

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

# --- Fast path: only process Bash tool calls ---

if [ "$tool_name" != "Bash" ]; then
  exit 0
fi

timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# --- Track issue state changes ---

if echo "$tool_command" | grep -qE 'gh\s+issue\s+(create|close|edit|reopen)'; then
  mkdir -p "$PROGRESS_DIR" 2>/dev/null

  # Extract action
  action=$(echo "$tool_command" | grep -oE 'gh\s+issue\s+(create|close|edit|reopen)' | awk '{print $3}')

  # Extract issue number if present
  issue_num=$(echo "$tool_command" | grep -oE 'gh\s+issue\s+\w+\s+[0-9]+' | awk '{print $4}')
  [ -z "$issue_num" ] && issue_num="unknown"

  echo "$timestamp | issue $action | #$issue_num" >> "$ACTIVITY_LOG"
fi

# --- Track context modifications ---

if echo "$tool_command" | grep -qF "$SDD_ROOT/context/"; then
  mkdir -p "$(dirname "$CONTEXT_TS")" 2>/dev/null
  echo "$timestamp" > "$CONTEXT_TS"
fi

# --- Post-hooks never block ---

exit 0
