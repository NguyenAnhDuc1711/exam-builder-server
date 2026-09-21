#!/usr/bin/env bash
# SessionStart hook: auto-start memory agent daemon if enabled and not running,
# then register the current project with the daemon.
# Fast path: PID check (~1ms). Registration ping is async (~0ms blocking).

set -uo pipefail

AGENT_DIR="$HOME/.config/sdd/memory-agent"
PID_FILE="$AGENT_DIR/.pid"
VENV_DIR="$AGENT_DIR/.venv"
LOG_FILE="$AGENT_DIR/.log"

# Resolve project root and memory agent port from config
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"
CONFIG=""
# Config lookup order: .sdd/ first, then legacy pre-migration locations (not .sdd state)
for cfg in "$PROJECT_ROOT/.sdd/config/lifecycle.json" \
           "$PROJECT_ROOT/.claude/config/lifecycle.json" \
           "$PROJECT_ROOT/config/lifecycle.json"; do
  [[ -f "$cfg" ]] && CONFIG="$cfg" && break
done
[[ -z "$CONFIG" ]] && exit 0

# Parse enabled flag (jq fast path, python3 fallback)
if command -v jq &>/dev/null; then
  jq -e '.memory_agent.enabled' "$CONFIG" &>/dev/null || exit 0
  PORT=$(jq -r '.memory_agent.port // 8888' "$CONFIG" 2>/dev/null)
else
  python3 -c "import json,sys;sys.exit(0 if json.load(open(sys.argv[1])).get('memory_agent',{}).get('enabled') else 1)" "$CONFIG" 2>/dev/null || exit 0
  PORT=$(python3 -c "import json;print(json.load(open('$CONFIG')).get('memory_agent',{}).get('port',8888))" 2>/dev/null || echo 8888)
fi
[[ "$PORT" == "null" || -z "$PORT" ]] && PORT=8888

# Register project with running daemon (async, non-blocking)
# Uses /query endpoint which calls get_project_root() → auto-registers
register_project() {
  curl -s --max-time 1 \
    -H "X-Project-Root: $PROJECT_ROOT" \
    "http://localhost:${PORT}/query?q=ping&limit=0" >/dev/null 2>&1 &
}

# 1. Already running? → register project and exit
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
  register_project
  exit 0
fi

# 2. Setup done? (venv + agent.py exist)
[[ -f "$VENV_DIR/bin/python" && -f "$AGENT_DIR/agent.py" ]] || exit 0

# 3. Clean stale PID file
[[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"

# 4. Start daemon in background (no port wait — keeps hook fast)
SDD_GLOBAL_DAEMON=1 nohup "$VENV_DIR/bin/python" "$AGENT_DIR/agent.py" --global \
  >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

# 5. Register project after short delay (daemon needs time to bind port)
(sleep 1 && curl -s --max-time 2 \
  -H "X-Project-Root: $PROJECT_ROOT" \
  "http://localhost:${PORT}/query?q=ping&limit=0" >/dev/null 2>&1) &

exit 0
