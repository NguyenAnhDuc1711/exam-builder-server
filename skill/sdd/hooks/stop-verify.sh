#!/usr/bin/env bash
# SDD Stop Hook: Ralph Loop Verification Enforcer
#
# Triggered when Claude attempts to end a session.
# Responsibilities:
#   1. Check for active SDD task — if none, allow exit silently
#   2. Read verify_mode from state (SKIP/RELAXED/STRICT)
#   3. Run the appropriate verification profile
#   4. Decision matrix: PASS → allow, FAIL+RELAXED → warn+allow,
#      FAIL+STRICT → block (exit 2), max iterations → BLOCKED.md+allow
#
# Usage:
#   bash hooks/stop-verify.sh [sdd_root]
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

# --- Step 1: Check for active task ---

state=$(read_verify_state 2>/dev/null || echo '{"active_task": null}')
active_task=""
if command -v jq &>/dev/null; then
  active_task=$(echo "$state" | jq -r '.active_task // empty' 2>/dev/null || echo "")
else
  active_task=$(python3 -c "
import json
d = json.loads('''$state''')
t = d.get('active_task')
print(json.dumps(t) if t else '')
" 2>/dev/null || echo "")
fi

if [ -z "$active_task" ] || [ "$active_task" = "null" ]; then
  # No active SDD task — allow exit silently
  exit 0
fi

# Parse state fields
if command -v jq &>/dev/null; then
  issue_number=$(echo "$state" | jq -r '.active_task.issue_number')
  verify_mode=$(echo "$state" | jq -r '.active_task.verify_mode')
  tech_stack=$(echo "$state" | jq -r '.active_task.tech_stack')
  current_iter=$(echo "$state" | jq -r '.active_task.current_iteration')
  max_iter=$(echo "$state" | jq -r '.active_task.max_iterations')
else
  issue_number=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_task']['issue_number'])" 2>/dev/null)
  verify_mode=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_task']['verify_mode'])" 2>/dev/null)
  tech_stack=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_task']['tech_stack'])" 2>/dev/null)
  current_iter=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_task']['current_iteration'])" 2>/dev/null)
  max_iter=$(python3 -c "import json; d=json.loads('''$state'''); print(d['active_task']['max_iterations'])" 2>/dev/null)
fi

# --- Step 2: Check verify mode ---

if [ "$verify_mode" = "SKIP" ]; then
  echo "⏭️ Verification skipped (mode=SKIP for task #$issue_number)"
  exit 0
fi

# --- Step 3: Check max iterations ---

if [ "$current_iter" -ge "$max_iter" ] 2>/dev/null; then
  echo ""
  echo "⚠️ ═══ MAX ITERATIONS REACHED ═══"
  echo "  Task #$issue_number: $current_iter/$max_iter iterations exhausted"
  echo "  Creating BLOCKED.md and allowing exit."
  echo ""

  # Create BLOCKED.md
  blocked_file="$SDD_ROOT/context/verify/BLOCKED.md"
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  {
    echo "# Verification BLOCKED"
    echo ""
    echo "- **Issue**: #$issue_number"
    echo "- **Iterations attempted**: $current_iter"
    echo "- **Max allowed**: $max_iter"
    echo "- **Blocked at**: $timestamp"
    echo "- **Tech stack**: $tech_stack"
    echo "- **Verify mode**: $verify_mode"
    echo ""
    echo "## Iteration History"
    echo ""
    if command -v jq &>/dev/null; then
      echo "$state" | jq -r '.active_task.iterations[] | "- Iteration \(.iteration) [\(.timestamp)]: \(.result) — failures: \(.failures | join(", "))"' 2>/dev/null
    else
      python3 -c "
import json
d = json.loads('''$state''')
for it in d['active_task'].get('iterations', []):
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
    new_state=$(echo "$state" | jq --arg ts "$timestamp" '.active_task.status = "blocked" | .active_task.blocked_at = $ts')
  else
    new_state=$(python3 -c "
import json
d = json.loads('''$state''')
d['active_task']['status'] = 'blocked'
d['active_task']['blocked_at'] = '$timestamp'
print(json.dumps(d, indent=2))
" 2>/dev/null)
  fi
  write_verify_state "$new_state"

  exit 0
fi

# --- Step 3.5: Pre-verify — Test Existence Check (Superpowers Integration) ---

if [ "$verify_mode" = "STRICT" ]; then
  _test_first_enabled=true
  _block_on_no_tests=true
  if read_config_bool "test_first" "enabled" "true" 2>/dev/null; then
    _test_first_enabled=true
  else
    _test_first_enabled=false
  fi
  if read_config_bool "test_first" "block_on_no_tests" "true" 2>/dev/null; then
    _block_on_no_tests=true
  else
    _block_on_no_tests=false
  fi

  if [ "$_test_first_enabled" = "true" ]; then
    # Read task type from state
    task_type=""
    if command -v jq &>/dev/null; then
      task_type=$(echo "$state" | jq -r '.active_task.type // empty')
    else
      task_type=$(python3 -c "
import json
d = json.loads('''$state''')
print(d.get('active_task', {}).get('type', ''))
" 2>/dev/null)
    fi

    if [ "$task_type" = "FEATURE" ]; then
      # Count test-related files in recent changes
      test_count=0
      changed_files=$(git diff --name-only HEAD~1 2>/dev/null || echo "")
      if [ -n "$changed_files" ]; then
        test_count=$(echo "$changed_files" | xargs grep -rlE 'test_|it\(|describe\(|func [Tt]est|@Test|#\[test\]|_test\.go|\.test\.|\.spec\.' 2>/dev/null | wc -l | tr -d ' ') || test_count=0
      fi

      if [ "$test_count" -eq 0 ] 2>/dev/null; then
        if [ "$_block_on_no_tests" = "true" ]; then
          echo ""
          echo "❌ ═══ BLOCKED: No test files found for FEATURE task #$issue_number ═══"
          echo ""
          echo "  FEATURE tasks require tests before completion."
          echo "  Write tests covering the acceptance criteria, then try again."
          echo ""
          # Check for Superpowers
          if detect_superpowers 2>/dev/null; then
            echo "  💡 Superpowers detected: Use the **tdd** skill for RED→GREEN→REFACTOR cycle."
          fi
          echo ""
          exit 2
        else
          echo ""
          echo "⚠️ WARNING: No test files found for FEATURE task #$issue_number"
          echo "  Consider adding tests for acceptance criteria."
          echo ""
        fi
      elif [ "$test_count" -lt 2 ] 2>/dev/null; then
        # Warn on low test count (heuristic threshold)
        if read_config_bool "test_first" "warn_on_low_test_count" "true" 2>/dev/null; then
          echo ""
          echo "⚠️ Low test count ($test_count file(s)) for FEATURE task #$issue_number"
          echo "  Ensure all acceptance criteria have test coverage."
          echo ""
        fi
      fi
    fi
  fi
fi

# --- Step 4: Run verification profile ---

profile_path=$(get_verify_profile "$tech_stack")

# Fallback to generic if profile doesn't exist
if [ ! -f "$profile_path" ]; then
  profile_path="$SDD_ROOT/context/verify/profiles/generic.sh"
fi

if [ ! -f "$profile_path" ]; then
  echo "⚠️ No verification profile found — allowing exit"
  exit 0
fi

echo ""
echo "═══ SDD Verify: Task #$issue_number (mode=$verify_mode, stack=$tech_stack) ═══"
echo ""

# Capture verify output
mkdir -p "$RESULTS_DIR" 2>/dev/null || true
verify_output=$(bash "$profile_path" "$SDD_ROOT" 2>&1) || true
verify_exit=$?

# Log result
log_file="$RESULTS_DIR/task-${issue_number}-verify.log"
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
{
  echo "=== Verify Run: $timestamp ==="
  echo "Profile: $profile_path"
  echo "Mode: $verify_mode"
  echo "Iteration: $((current_iter + 1))/$max_iter"
  echo "Exit code: $verify_exit"
  echo "---"
  echo "$verify_output"
  echo ""
} >> "$log_file"

# --- Step 5: Decision matrix ---

# Check for VERIFY_PASS in output
if echo "$verify_output" | grep -q "VERIFY_PASS"; then
  echo "$verify_output"
  echo ""

  # --- Post-verify: Mini Semantic Review (Superpowers Integration) ---
  if read_config_bool "semantic_review" "enabled" "true" 2>/dev/null; then
    # Read task type from state
    _sr_task_type=""
    if command -v jq &>/dev/null; then
      _sr_task_type=$(echo "$state" | jq -r '.active_task.type // empty')
    else
      _sr_task_type=$(python3 -c "
import json
d = json.loads('''$state''')
print(d.get('active_task', {}).get('type', ''))
" 2>/dev/null)
    fi

    if [[ "$_sr_task_type" =~ ^(FEATURE|REFACTOR|ENHANCEMENT)$ ]]; then
      echo ""
      echo "═══════════════════════════════════════════════════════"
      echo "  MINI SEMANTIC REVIEW"
      echo "═══════════════════════════════════════════════════════"
      echo ""

      if detect_superpowers 2>/dev/null; then
        echo "💡 Superpowers detected: Invoke **code-review** skill for 2-stage review:"
        echo "  Stage 1: Spec compliance check"
        echo "  Stage 2: Code quality review"
      else
        # Inject self-review checklist from prompt file
        _review_file="$SDD_ROOT/prompts/task-semantic-review.md"
        if [ -f "$_review_file" ]; then
          _review_content=$(cat "$_review_file")
          echo "${_review_content//\{N\}/$issue_number}"
        else
          echo "Self-review checklist not found at: $_review_file"
          echo "Perform a manual review of acceptance criteria before closing."
        fi
      fi

      echo ""
      echo "Complete the review above. Any 'NO' → add to handoff 'Warnings for Next Task'."
      echo "═══════════════════════════════════════════════════════"
      echo ""
    fi
  fi

  echo "✅ Verification passed — allowing exit"
  exit 0
fi

# VERIFY_FAIL path
echo "$verify_output"
echo ""

# Extract failure details for iteration logging
failures=$(echo "$verify_output" | grep "❌" | head -5 | tr '\n' ',' | sed 's/,$//')
files_changed=$(git diff --name-only HEAD~1 2>/dev/null | tr '\n' ',' | sed 's/,$//' || echo "unknown")

# Increment iteration
increment_iteration "VERIFY_FAIL" "$failures" "$files_changed" >/dev/null 2>&1
new_iter=$((current_iter + 1))

if [ "$verify_mode" = "RELAXED" ]; then
  echo "⚠️ ═══ VERIFICATION FAILED (RELAXED mode) ═══"
  echo "  Task #$issue_number: Iteration $new_iter/$max_iter"
  echo "  Mode is RELAXED — allowing exit with warning."
  echo "  Fix the issues above before closing the task."
  echo ""
  exit 0
fi

# STRICT mode — block exit using Stop hook JSON API
block_reason="❌ VERIFICATION FAILED — EXIT BLOCKED

Task #$issue_number: Iteration $new_iter/$max_iter
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
  # Escape for JSON manually
  escaped_reason=$(printf '%s' "$block_reason" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null)
  printf '{"decision":"block","reason":%s}\n' "$escaped_reason"
fi

exit 2
