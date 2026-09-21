#!/usr/bin/env bash
# SDD Stop Hook: Epic-Level Ralph Loop Verification Enforcer
#
# Triggered when Claude attempts to end a session during epic verification.
# Responsibilities:
#   1. Check for active epic verify — if none, allow exit silently
#   2. Read verify_mode from epic-state.json
#   3. Run epic-verify.sh (4-tier test runner)
#   4. Decision matrix:
#      - EPIC_VERIFY_PASS → allow exit (exit 0)
#      - EPIC_VERIFY_FAIL + STRICT → block exit (exit 2)
#      - EPIC_VERIFY_FAIL + RELAXED → warn + allow (exit 0)
#      - EPIC_VERIFY_PARTIAL → warn + allow (developer decision)
#      - Max iterations → BLOCKED.md + allow (exit 0)
#   5. Mid-loop clear at configurable iteration
#
# Usage:
#   bash hooks/stop-epic-verify.sh [sdd_root]
#
# Exit codes:
#   0 = allow exit
#   2 = BLOCK exit (Claude Code hook API — forces Claude back into fix loop)

set -uo pipefail

# SAFETY: If anything unexpected fails, always allow exit (don't trap Claude in a loop)
trap 'exit 0' ERR

# Drain stdin (Claude Code sends JSON context via Stop hook API)
HOOK_INPUT=$(cat 2>/dev/null || true)

SDD_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RESULTS_DIR="$SDD_ROOT/context/verify/results"

# Source lifecycle helpers
HELPERS="$SDD_ROOT/scripts/pm/lifecycle-helpers.sh"
if [ ! -f "$HELPERS" ]; then
  # No helpers = can't verify, allow exit
  exit 0
fi
source "$HELPERS"

# --- Step 1: Check for active epic verify ---

state=$(read_epic_verify_state 2>/dev/null || echo '{"active_epic": null}')
active_epic=""
if command -v jq &>/dev/null; then
  active_epic=$(echo "$state" | jq -r '.active_epic // empty' 2>/dev/null || echo "")
else
  active_epic=$(python3 -c "
import json
d = json.loads('''$state''')
t = d.get('active_epic')
print(json.dumps(t) if t else '')
" 2>/dev/null || echo "")
fi

if [ -z "$active_epic" ] || [ "$active_epic" = "null" ]; then
  # No active epic verify — allow exit silently
  exit 0
fi

# Parse state fields
if command -v jq &>/dev/null; then
  epic_name=$(echo "$state" | jq -r '.active_epic.epic_name')
  verify_mode=$(echo "$state" | jq -r '.active_epic.verify_mode')
  current_iter=$(echo "$state" | jq -r '.active_epic.current_iteration')
  max_iter=$(echo "$state" | jq -r '.active_epic.max_iterations')
  mid_clear_at=$(echo "$state" | jq -r '.active_epic.mid_clear_at')
else
  epic_name=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_epic']['epic_name'])" 2>/dev/null)
  verify_mode=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_epic']['verify_mode'])" 2>/dev/null)
  current_iter=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_epic']['current_iteration'])" 2>/dev/null)
  max_iter=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_epic']['max_iterations'])" 2>/dev/null)
  mid_clear_at=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_epic']['mid_clear_at'])" 2>/dev/null)
fi

# --- Step 2: Check max iterations ---

if [ "$current_iter" -ge "$max_iter" ] 2>/dev/null; then
  echo ""
  echo "⚠️ ═══ EPIC MAX ITERATIONS REACHED ═══"
  echo "  Epic '$epic_name': $current_iter/$max_iter iterations exhausted"
  echo "  Creating BLOCKED.md and allowing exit."
  echo ""

  # Create BLOCKED.md
  blocked_file="$SDD_ROOT/context/verify/BLOCKED.md"
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  {
    echo "# Epic Verification BLOCKED"
    echo ""
    echo "- **Epic**: $epic_name"
    echo "- **Iterations attempted**: $current_iter"
    echo "- **Max allowed**: $max_iter"
    echo "- **Blocked at**: $timestamp"
    echo "- **Verify mode**: $verify_mode"
    echo ""
    echo "## Iteration History"
    echo ""
    if command -v jq &>/dev/null; then
      echo "$state" | jq -r '.active_epic.iterations[] | "- Iteration \(.iteration) [\(.timestamp)]: \(.result) — failures: \(.failures | join(", "))"' 2>/dev/null
    else
      python3 -c "
import json
d = json.loads('''$state''')
for it in d['active_epic'].get('iterations', []):
    fails = ', '.join(it.get('failures', []))
    print(f\"- Iteration {it['iteration']} [{it['timestamp']}]: {it['result']} — failures: {fails}\")
" 2>/dev/null
    fi
    echo ""
    echo "## Next Steps"
    echo "- Review the failure patterns above"
    echo "- Consider manual debugging or a different approach"
    echo "- Run \`/pm:verify-skip\` to bypass verification if appropriate"
  } > "$blocked_file"

  # Update state to blocked
  if command -v jq &>/dev/null; then
    new_state=$(echo "$state" | jq --arg ts "$timestamp" '.active_epic.status = "blocked" | .active_epic.blocked_at = $ts')
  else
    new_state=$(python3 -c "
import json
d = json.loads('''$state''')
d['active_epic']['status'] = 'blocked'
d['active_epic']['blocked_at'] = '$timestamp'
print(json.dumps(d, indent=2))
" 2>/dev/null)
  fi
  write_epic_verify_state "$new_state"

  exit 0
fi

# --- Step 3: Mid-loop clear check ---

next_iter=$((current_iter + 1))
if [ "$next_iter" -eq "$mid_clear_at" ] 2>/dev/null; then
  echo ""
  echo "═══ MID-LOOP CLEAR (Iteration $next_iter/$max_iter) ═══"

  # Save summary for reload after clear
  summary_file="$SDD_ROOT/context/verify/epic-mid-clear-summary.md"
  {
    echo "# Epic Verify Mid-Clear Summary"
    echo ""
    echo "- **Epic**: $epic_name"
    echo "- **Iteration**: $next_iter/$max_iter"
    echo "- **Previous attempts**: $current_iter"
    echo ""
    echo "## Recent Failures"
    if command -v jq &>/dev/null; then
      echo "$state" | jq -r '.active_epic.iterations[-3:][] | "- Iteration \(.iteration): \(.result) — \(.failures | join(", "))"' 2>/dev/null
    else
      python3 -c "
import json
d = json.loads('''$state''')
for it in d['active_epic'].get('iterations', [])[-3:]:
    fails = ', '.join(it.get('failures', []))
    print(f\"- Iteration {it['iteration']}: {it['result']} — {fails}\")
" 2>/dev/null
    fi
    echo ""
    echo "## Guidance"
    echo "Bạn đang ở iteration $next_iter. Previous attempts đã fail. Thử approach khác."
  } > "$summary_file"

  # Output JSON signal for Claude Code to clear context
  if command -v jq &>/dev/null; then
    jq -n \
      --arg epic "$epic_name" \
      --argjson iter "$next_iter" \
      --arg summary "$summary_file" \
      '{"decision":"block","reason":"mid_loop_clear","epic":$epic,"iteration":$iter,"reload_files":[$summary]}'
  else
    printf '{"decision":"block","reason":"mid_loop_clear","epic":"%s","iteration":%d,"reload_files":["%s"]}\n' \
      "$epic_name" "$next_iter" "$summary_file"
  fi

  exit 2
fi

# --- Step 4: Run epic-verify.sh ---

verify_script="$SDD_ROOT/context/verify/epic-verify.sh"

if [ ! -f "$verify_script" ]; then
  echo "⚠️ Epic verify script not found — allowing exit"
  exit 0
fi

echo ""
echo "═══ SDD Epic Verify: '$epic_name' (mode=$verify_mode, iter=$next_iter/$max_iter) ═══"
echo ""

# Capture verify output
mkdir -p "$RESULTS_DIR" 2>/dev/null || true
verify_output=$(bash "$verify_script" "$epic_name" 2>&1) || true
verify_exit=$?

# Log result
log_file="$RESULTS_DIR/epic-${epic_name}-verify.log"
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
{
  echo "=== Epic Verify Run: $timestamp ==="
  echo "Script: $verify_script"
  echo "Mode: $verify_mode"
  echo "Iteration: $next_iter/$max_iter"
  echo "Exit code: $verify_exit"
  echo "---"
  echo "$verify_output"
  echo ""
} >> "$log_file"

# --- Step 5: Decision matrix ---

# EPIC_VERIFY_PASS (exit 0)
if echo "$verify_output" | grep -q "EPIC_VERIFY_PASS"; then
  echo "$verify_output"
  echo ""
  echo "✅ Epic verification passed — allowing exit"
  exit 0
fi

# EPIC_VERIFY_PARTIAL (exit 2) — warn + allow (developer decision)
if echo "$verify_output" | grep -q "EPIC_VERIFY_PARTIAL"; then
  echo "$verify_output"
  echo ""

  # Extract failure details for iteration logging
  failures=$(echo "$verify_output" | grep "⚠️" | head -5 | tr '\n' ',' | sed 's/,$//')
  files_changed=$(git diff --name-only HEAD~1 2>/dev/null | tr '\n' ',' | sed 's/,$//' || echo "unknown")
  increment_epic_iteration "EPIC_VERIFY_PARTIAL" "$failures" "$files_changed" >/dev/null 2>&1

  echo "⚠️ ═══ EPIC VERIFICATION PARTIAL ═══"
  echo "  Epic '$epic_name': Iteration $next_iter/$max_iter"
  echo "  Some non-blocking tiers failed."
  echo "  Developer decision: continue fixing or exit."
  echo ""
  exit 0
fi

# EPIC_VERIFY_FAIL path
echo "$verify_output"
echo ""

# Extract failure details for iteration logging
failures=$(echo "$verify_output" | grep "❌" | head -5 | tr '\n' ',' | sed 's/,$//')
files_changed=$(git diff --name-only HEAD~1 2>/dev/null | tr '\n' ',' | sed 's/,$//' || echo "unknown")
increment_epic_iteration "EPIC_VERIFY_FAIL" "$failures" "$files_changed" >/dev/null 2>&1

if [ "$verify_mode" = "RELAXED" ]; then
  echo "⚠️ ═══ EPIC VERIFICATION FAILED (RELAXED mode) ═══"
  echo "  Epic '$epic_name': Iteration $next_iter/$max_iter"
  echo "  Mode is RELAXED — allowing exit with warning."
  echo "  Fix the issues above before closing the epic."
  echo ""
  exit 0
fi

# STRICT mode — block exit
block_reason="❌ EPIC VERIFICATION FAILED — EXIT BLOCKED

Epic '$epic_name': Iteration $next_iter/$max_iter
Mode: STRICT — you must fix the failures before completing.

What to do:
  1. Read the errors above carefully
  2. Fix the failing checks
  3. Try completing again

To skip verification: /pm:verify-skip <reason>
To check status: /pm:verify-status"

echo "$block_reason" >&2

# Output JSON for Stop hook API (decision: block)
if command -v jq &>/dev/null; then
  jq -n --arg reason "$block_reason" '{"decision":"block","reason":$reason}'
else
  escaped_reason=$(printf '%s' "$block_reason" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null)
  printf '{"decision":"block","reason":%s}\n' "$escaped_reason"
fi

exit 2
