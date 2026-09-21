# QA

Create and execute QA test scenarios. This reference is loaded by `verify.md` during Phase B QA tier.

## Tool Enforcement

**CRITICAL:** ALL iOS simulator interactions MUST go through Bash shell wrappers below. DO NOT use MCP tools (XcodeBuildMCP, etc.) for screenshot, UI tree, tap, swipe, or any simulator interaction — MCP screenshot tools are slower and lack tap/swipe/UI tree capabilities.

Required shell wrappers (called via Bash tool with `source`):
- `scripts/qa/axe-wrapper.sh` — `axe_screenshot`, `axe_describe_ui`, `axe_tap`, `axe_tap_id`, `axe_type`, `axe_swipe`, `axe_batch`
- `scripts/qa/simctl-wrapper.sh` — `simctl_auto_detect`, `simctl_list_booted`
- `scripts/qa/evidence-capture.sh` — `capture_step_evidence`, `capture_before_after`
- `scripts/qa/diff-detect.sh` — `detect_and_filter`

---

## qa:scenario-new

Scaffold a new QA scenario file at `.sdd/qa/scenarios/{name}.md`.

### Supported Keywords

#### Vietnamese
- `mở` — open/launch an app or screen
- `chọn` — select/choose an element or option
- `kiểm tra` — verify/check a condition
- `vuốt` — swipe gesture

#### English
- `tap` — tap a UI element
- `verify` — assert a condition is true
- `swipe` — swipe gesture
- `launch` — launch app or screen
- `type` — enter text into a field
- `check` — check a condition
- `open` — open a screen or item
- `select` — select an element or option

### Step Format

- Arrow notation: `action → assertion` (e.g., `Tap 'Login' → verify home screen displayed`)
- Quoted elements: use single quotes around UI element labels (e.g., `'Start Quiz'`)
- Steps are numbered: `1.`, `2.`, etc.

### Frontmatter Fields

| Field        | Required | Values                                                             |
|--------------|----------|--------------------------------------------------------------------|
| `name`       | yes      | kebab-case identifier                                              |
| `screens`    | yes      | array of screen names (e.g., `[HomeView, QuizView]`)              |
| `priority`   | yes      | `high`, `medium`, or `low`                                        |
| `categories` | yes      | array, subset of: `ui_layout`, `navigation_flow`, `data_display`, `accessibility` |

### Instructions

1. **Get scenario name:**
   - If `$ARGUMENTS` is non-empty, use it as the scenario name.
   - Otherwise, ask: `Enter scenario name (kebab-case, e.g. "login-flow"):`
   - Validate: name MUST match `^[a-z0-9][a-z0-9-]*[a-z0-9]$`. If invalid → print `❌ Name must be kebab-case (e.g. "login-flow"). Got: '{name}'` and stop.

2. **Check for duplicate:**
   ```bash
   test -f .sdd/qa/scenarios/{name}.md && echo "⚠️ Scenario '{name}' already exists. Overwrite? (yes/no)"
   ```
   If no → stop.

3. **Collect metadata:**
   Ask the user for:
   - **Target screens** (comma-separated, e.g., `HomeView, LoginView`)
   - **Priority** (`high`, `medium`, or `low`)
   - **Categories** (comma-separated from: `ui_layout`, `navigation_flow`, `data_display`, `accessibility`)
   - Validate categories — warn and filter out any values not in the valid set.
   - At least one category is required.

4. **Collect steps:**
   - Ask: `Describe the test steps (numbered list, or press Enter to use template):`
   - If user provides steps, use them.
   - If empty, use the template steps below.
   - At least 1 step is required. If none provided and user skips template → print `❌ At least one step is required.` and stop.

5. **Ensure directory:**
   ```bash
   mkdir -p .sdd/qa/scenarios 2>/dev/null
   ```

6. **Write scenario file** to `.sdd/qa/scenarios/{name}.md`:

```markdown
---
name: {name}
screens: [{screen1}, {screen2}]
priority: {priority}
categories: [{cat1}, {cat2}]
---
# {Title Case of name}
{numbered steps}
```

**Template steps** (used when user skips step input):
```
1. Mở app → verify main screen visible
2. Tap '{Primary Action}' → verify expected screen displayed
3. Kiểm tra key elements visible on screen
4. Verify data displayed correctly
5. Tap back → verify returns to previous screen
```

7. **Confirm:**
   ```
   ✅ Scenario created: .sdd/qa/scenarios/{name}.md
   Next: qa:run {name}
   ```

---

## qa:run

Orchestrate the full QA pipeline: discover scenarios, parse steps, setup simulator, execute steps via shell wrappers, evaluate UI state (Claude Code as LLM-as-judge), compute health score, and generate markdown report.

### Usage

```
qa:run                      # Run all scenarios
qa:run {name}               # Run named scenario only
qa:run --diff-aware         # Run only scenarios for changed screens
qa:run --diff-aware {name}  # Intersection of diff-aware + name filter
```

### Quick Check

1. Load config:
   ```bash
   if [ -f config/qa.json ]; then
     cat config/qa.json
   else
     echo '{"enabled":true,"default_timeout":300,"health_score_threshold":70,"category_weights":{"ui_layout":25,"navigation_flow":25,"data_display":25,"accessibility":25},"evidence_retention_runs":10}'
   fi
   ```
   If config missing, use hardcoded defaults and warn: `"⚠️ config/qa.json not found, using defaults"`

2. Check scenario directory:
   ```bash
   test -d .sdd/qa/scenarios || echo "❌ No scenarios: .sdd/qa/scenarios/ not found. Run: qa:scenario-new"
   ```

3. Ensure output directories:
   ```bash
   mkdir -p .sdd/qa/reports .sdd/qa/evidence 2>/dev/null
   ```

### Instructions

Execute all 7 phases sequentially. Track start time for duration calculation.

```bash
QA_START=$(date +%s)
RUN_ID=$(date -u +"%Y%m%d-%H%M%S")
```

### Phase 1 — Discover

**Check for `--diff-aware` flag** in `$ARGUMENTS`:
```bash
DIFF_AWARE=false
NAME_FILTER=""
if echo "${ARGUMENTS:-}" | grep -q -- '--diff-aware'; then
  DIFF_AWARE=true
  NAME_FILTER=$(echo "${ARGUMENTS:-}" | sed 's/--diff-aware//g' | xargs)
else
  NAME_FILTER="${ARGUMENTS:-}"
fi
```

**If `--diff-aware` is set**, use diff detection to get filtered scenario list:
```bash
source scripts/qa/diff-detect.sh
DIFF_RESULT=$(detect_and_filter)
# Parse scenario list from DIFF_RESULT["data"]["scenarios"]
# Note whether fallback was triggered (run all) and log accordingly:
#   Fallback: "Diff-aware: no screen changes detected — running all N scenarios"
#   Filtered: "Diff-aware: {M}/{N} scenarios selected based on changed files"
```
Use the returned scenario list as the candidate set for further filtering.

**If `--diff-aware` is NOT set**, find all scenario files:
```bash
ls .sdd/qa/scenarios/*.md 2>/dev/null
```

If `$NAME_FILTER` is non-empty, apply name filter to the candidate set:
```bash
# Filter candidate scenarios to those matching NAME_FILTER in filename
```

- If no scenarios found: print `"❌ No scenarios found in .sdd/qa/scenarios/"` and stop.
- If name filter specified and no match: print `"❌ Scenario '${NAME_FILTER}' not found"` and stop.
- Print: `"Found {N} scenario(s): {list}"`

### Phase 2 — Parse

For each discovered scenario file:

1. Read the file content.
2. Extract YAML frontmatter fields: `name`, `screens`, `priority`, `categories`.
3. Parse numbered steps (lines matching `^\d+\.`).
4. For each step, decompose into action + assertion:
   - Split at ` → ` (arrow with spaces) to get `action_part` and `assertion_part`.
   - If no arrow, the entire line is both action and assertion.
   - Detect action keyword from action_part:
     - Vietnamese: `mở`/`launch`/`open` → `launch`, `chọn`/`select`/`tap` → `tap`, `kiểm tra`/`verify`/`check` → `verify`, `vuốt`/`swipe` → `swipe`, `type` → `type`
     - Default → `verify` (if no action keyword detected, treat as verify-only step)
   - Extract quoted element labels: text within single quotes `'...'`.
   - Build step object: `{action, target, assertion, raw_text}`

If a scenario fails to parse (no steps, invalid format): log `"⚠️ Skipping {name}: parse error"` and continue.

### Phase 3 — Setup

Verify AXe CLI is installed:
```bash
command -v axe >/dev/null 2>&1 || { echo "❌ AXe CLI not found. Install: brew tap cameroncooke/axe && brew install cameroncooke/axe/axe"; exit 1; }
```
If AXe is missing, print the error and stop — do NOT fall back to MCP tools.

Verify simulator is ready:
```bash
source scripts/qa/simctl-wrapper.sh
simctl_auto_detect
```

Parse the JSON response. If `success` is false: print the error and ask user to boot a simulator manually.

Store the UDID from the response for use in subsequent phases.

Verify the simulator is responding by running a quick describe-ui:
```bash
source scripts/qa/axe-wrapper.sh
axe_describe_ui "$UDID"
```

If this fails, print error and stop.

### Phase 4 — Execute

For each scenario, for each parsed step:

1. **Source wrappers:**
   ```bash
   source scripts/qa/evidence-capture.sh
   ```

2. **Execute based on action type:**
   - `launch`: No shell action needed (app should already be running). Capture current state.
   - `tap`: Call `capture_before_after "$RUN_ID" "$STEP_N" "tap" "$TARGET" "$UDID"`
   - `type`: Call `capture_before_after "$RUN_ID" "$STEP_N" "type" "$TEXT" "$UDID"`
   - `swipe`: Call `capture_before_after "$RUN_ID" "$STEP_N" "swipe" "$DIRECTION" "$UDID"`
   - `verify`: No action — capture state only: `capture_step_evidence "$RUN_ID" "$STEP_N" "axe" "$UDID"`

3. **Collect evidence paths** from the JSON response for Phase 5.

4. **Handle errors:** If the shell wrapper returns `{"success": false}`, mark the step as FAIL with the error message. Do NOT stop — continue to next step.

### Phase 5 — Evaluate

For each step, evaluate using **dual signal** (accessibility tree + screenshot):

1. **Read the accessibility tree JSON file** from the evidence directory:
   - For action steps: read `after-accessibility-tree.json`
   - For verify-only steps: read `accessibility-tree.json`

2. **Read the screenshot file** from the evidence directory:
   - For action steps: read `after-screenshot.png`
   - For verify-only steps: read `screenshot.png`

3. **Evaluate the assertion** by analyzing BOTH signals:
   - Parse the assertion text to understand what should be true.
   - Check the accessibility tree JSON for expected elements, labels, and states.
   - Examine the screenshot visually for UI correctness.
   - Consider both signals together — they should corroborate.

4. **Produce verdict:**
   ```
   result: PASS | FAIL | UNCERTAIN
   confidence: 0-100
   reasoning: brief explanation of why this verdict was reached
   ```

   Guidelines:
   - **PASS** (confidence >= 60): Both accessibility tree AND visual confirm the assertion.
   - **FAIL** (confidence >= 60): Clear evidence that the assertion does NOT hold.
   - **UNCERTAIN** (confidence < 60): Ambiguous evidence or conflicting signals between tree and screenshot.

5. **For steps where shell wrapper returned error:** Mark as FAIL with confidence 100 and reason = the error message.

### Phase 6 — Score

Compute health score using category weights from config:

1. **Group steps by category** from each scenario's frontmatter `categories` field.
   - A step belongs to ALL categories listed in its scenario's frontmatter.

2. **Per-category score:**
   ```
   category_score = (passing_steps_in_category / total_steps_in_category) * 100
   ```

3. **Overall health score:**
   - Only include categories that have at least one step.
   - Weight using `category_weights` from config (default: 25% each).
   - Normalize weights to sum to 100% across active categories only.
   ```
   active_weight_sum = sum of weights for categories with steps
   health_score = sum(category_score * weight / active_weight_sum) for each active category
   ```

4. Round to nearest integer.

### Phase 7 — Report

Calculate duration:
```bash
QA_END=$(date +%s)
DURATION=$((QA_END - QA_START))
```

Write markdown report to `.sdd/qa/reports/${RUN_ID}.md`:

```markdown
# QA Report: {RUN_ID}
**Health Score: {score}/100** | {pass_count}/{total_count} steps passed
Categories: UI Layout {score}% | Navigation {score}% | Data {score}% | A11y {score}%
Generated: {ISO timestamp} | Duration: {DURATION}s
Diff-aware: {M}/{N} scenarios selected based on changed files | OR | Diff-aware: disabled
---
## Per-Scenario Results
### {scenario-name} — {PASS|FAIL}
A scenario is PASS only if ALL steps passed.

| Step | Action | Result | Confidence | Details |
|------|--------|--------|------------|---------|
| 1 | {action description} | {PASS/FAIL/UNCERTAIN} | {N}% | {reasoning} |

## Accessibility Findings
List any accessibility-specific findings from evaluation:
- Elements missing accessibility labels
- Poor contrast or layout issues detected
- Tab order / focus order problems
If no accessibility issues found: "No accessibility issues detected."

## Recommendations
Based on failures, provide actionable recommendations:
- Specific elements that need fixing
- Missing UI states
- Suggested improvements
If all passed: "All scenarios passed. No recommendations."
```

### Output

```
✅ QA run complete: {RUN_ID}
   Health Score: {score}/100
   Passed: {pass_count}/{total_count} steps
   Report: .sdd/qa/reports/{RUN_ID}.md
   Duration: {N}s
```

### Edge Cases

- **No scenarios found** → `"❌ No scenarios in .sdd/qa/scenarios/"`
- **Scenario parse failure** → skip with `⚠️`, continue others
- **AXe CLI missing** → print install instructions and stop; do NOT fall back to MCP tools
- **Shell wrapper error** → mark step FAIL with error details, continue
- **All steps UNCERTAIN** → flag scenario for human review in report
- **Config missing** → use hardcoded defaults, warn once
- **Evidence directory creation fails** → continue without evidence, note in report
- **Simulator not booted** → try `simctl_auto_detect` first, then ask user
