#!/usr/bin/env bash
set -euo pipefail

VERSION="1.1.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Flags
HOOKS=false
UNINSTALL=false
UPGRADE=false
WITH_MEMORY=false

# Parse arguments — separate flags from positional
parse_args() {
  local positional=()
  for arg in "$@"; do
    case "$arg" in
      --help|-h) usage; exit 0 ;;
      --hooks)   HOOKS=true ;;
      --uninstall) UNINSTALL=true ;;
      --upgrade) UPGRADE=true ;;
      --with-memory) WITH_MEMORY=true ;;
      -*) echo "❌ Unknown flag: $arg"; usage; exit 1 ;;
      *)  positional+=("$arg") ;;
    esac
  done
  local target="${positional[0]:-.}"
  PROJECT_ROOT="$(cd "$target" 2>/dev/null && pwd)" || {
    echo "❌ Target directory does not exist: $target" >&2
    exit 1
  }
}

usage() {
  cat <<'USAGE'
SDD Installer v1.1.0

Usage: install.sh [options] [target_dir]

Options:
  --help, -h     Show this help message
  --hooks        Also install Claude Code hooks into .claude/settings.json
  --with-memory  Also install the global Memory Agent daemon
                 (~/.config/sdd/memory-agent/ — cross-session memory).
                 Needs Python 3.10+; warns and skips if unavailable.
  --upgrade      Replace skill files, preserve .sdd/ data
  --uninstall    Remove SDD skill files and .sdd/ directory

Examples:
  bash install.sh                       # Install into current directory
  bash install.sh --hooks               # Install with Claude Code hooks
  bash install.sh --with-memory         # Install + global Memory Agent daemon
  bash install.sh --hooks --with-memory # Install with hooks + Memory Agent
  bash install.sh --upgrade             # Upgrade skill files in-place
  bash install.sh --uninstall           # Remove SDD
  bash install.sh /path/to/project      # Install into specific directory
USAGE
}

# --- Uninstall ---
do_uninstall() {
  echo "Remove SDD from $PROJECT_ROOT?"
  echo "  This will delete: skill/sdd/ and .sdd/"
  printf "  Continue? (y/N) "
  read -r confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Cancelled."
    exit 0
  fi

  local removed=()
  if [[ -d "$PROJECT_ROOT/skill/sdd" ]]; then
    rm -rf "$PROJECT_ROOT/skill/sdd"
    removed+=("skill/sdd/")
  fi
  if [[ -d "$PROJECT_ROOT/.sdd" ]]; then
    rm -rf "$PROJECT_ROOT/.sdd"
    removed+=(".sdd/")
  fi
  if [[ -L "$PROJECT_ROOT/.claude/skills/sdd" ]]; then
    rm "$PROJECT_ROOT/.claude/skills/sdd"
    removed+=(".claude/skills/sdd symlink")
  fi

  # Remove bridge file sections
  remove_bridge_files

  # Remove hooks (scripts + settings entries)
  if [[ -d "$PROJECT_ROOT/.claude/hooks/sdd" ]] || \
     ([ -f "$PROJECT_ROOT/.claude/settings.json" ] && grep -q ".claude/hooks/sdd" "$PROJECT_ROOT/.claude/settings.json" 2>/dev/null); then
    remove_hooks
    removed+=(".claude/hooks/sdd/ + hook entries")
  fi

  if [[ ${#removed[@]} -eq 0 ]]; then
    echo "Nothing to remove — SDD not installed."
  else
    echo "✅ Uninstalled:"
    for r in "${removed[@]}"; do echo "  - $r"; done
  fi
}

# --- Hooks ---
# Deploy hook scripts to .claude/hooks/sdd/ (namespaced)
deploy_hooks() {
  local hooks_src="$PROJECT_ROOT/skill/sdd/hooks"
  local hooks_dest="$PROJECT_ROOT/.claude/hooks/sdd"
  [[ -d "$hooks_src" ]] || return

  mkdir -p "$hooks_dest"
  cp "$hooks_src/"*.sh "$hooks_dest/" 2>/dev/null || true
  chmod +x "$hooks_dest/"*.sh 2>/dev/null || true
  echo "  - Deployed hooks to .claude/hooks/sdd/"
}

# Register hooks in .claude/settings.json
install_hooks() {
  local settings="$PROJECT_ROOT/.claude/settings.json"
  local tmpl="$PROJECT_ROOT/skill/sdd/bridges/settings.json.tmpl"
  mkdir -p "$PROJECT_ROOT/.claude"

  if [[ ! -f "$settings" ]]; then
    # No settings.json — create from template or inline
    if [[ -f "$tmpl" ]]; then
      cp "$tmpl" "$settings"
      echo "  - Created .claude/settings.json from template"
    else
      # Inline fallback with all hooks
      cat > "$settings" <<'SETTINGS'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/bash-worktree-fix.sh",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/pre-tool-use.sh",
            "timeout": 10
          },
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/pre-tool-use-epic.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/post-tool-use.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/session-start-memory.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/stop-verify.sh",
            "timeout": 120
          },
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/stop-epic-verify.sh",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
SETTINGS
      echo "  - Created .claude/settings.json with hooks"
    fi
    return
  fi

  # settings.json exists — merge hooks using jq if available
  if ! grep -q ".claude/hooks/sdd" "$settings" 2>/dev/null; then
    if command -v jq &>/dev/null; then
      local tmp
      tmp=$(mktemp)
      # Merge all SDD hook groups
      local pre_hooks='{"matcher":"Bash","hooks":[{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/bash-worktree-fix.sh","timeout":5},{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/pre-tool-use.sh","timeout":10},{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/pre-tool-use-epic.sh","timeout":10}]}'
      local post_hooks='{"hooks":[{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/post-tool-use.sh","timeout":10}]}'
      local session_hooks='{"hooks":[{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/session-start-memory.sh","timeout":5}]}'
      local stop_hooks='{"hooks":[{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/stop-verify.sh","timeout":120},{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/sdd/stop-epic-verify.sh","timeout":120}]}'

      jq --argjson pre "$pre_hooks" --argjson post "$post_hooks" \
         --argjson session "$session_hooks" --argjson stop "$stop_hooks" '
        .hooks.PreToolUse = (.hooks.PreToolUse // []) + [$pre] |
        .hooks.PostToolUse = (.hooks.PostToolUse // []) + [$post] |
        .hooks.SessionStart = (.hooks.SessionStart // []) + [$session] |
        .hooks.Stop = (.hooks.Stop // []) + [$stop]
      ' "$settings" > "$tmp" && mv "$tmp" "$settings"
      echo "  - Updated .claude/settings.json with SDD hooks"
    else
      echo "  ⚠️  jq not found — cannot merge hooks into existing settings.json"
      echo "    Add SDD hooks manually. See: skill/sdd/hooks/README.md"
    fi
  else
    echo "  - SDD hooks already registered in .claude/settings.json"
  fi
}

# Install settings.local.json (user-local: permissions + hooks, always overwrites)
install_settings_local() {
  local settings_local="$PROJECT_ROOT/.claude/settings.local.json"
  local tmpl="$PROJECT_ROOT/skill/sdd/bridges/settings.local.json.tmpl"
  mkdir -p "$PROJECT_ROOT/.claude"

  if [[ -f "$tmpl" ]]; then
    cp "$tmpl" "$settings_local"
    echo "  - Deployed .claude/settings.local.json from template"
  else
    echo "  ⚠️  settings.local.json.tmpl not found — skipping"
  fi
}

remove_hooks() {
  local settings="$PROJECT_ROOT/.claude/settings.json"
  [[ -f "$settings" ]] || return

  # Remove hook scripts
  if [[ -d "$PROJECT_ROOT/.claude/hooks/sdd" ]]; then
    rm -rf "$PROJECT_ROOT/.claude/hooks/sdd"
  fi

  # Remove hook entries from settings.json
  if command -v jq &>/dev/null && grep -q ".claude/hooks/sdd" "$settings" 2>/dev/null; then
    local tmp
    tmp=$(mktemp)
    jq '
      .hooks.PreToolUse = [.hooks.PreToolUse[]? | select(.hooks[]?.command | test("\\.claude/hooks/sdd") | not)] |
      .hooks.PostToolUse = [.hooks.PostToolUse[]? | select(.hooks[]?.command | test("\\.claude/hooks/sdd") | not)] |
      .hooks.SessionStart = [.hooks.SessionStart[]? | select(.hooks[]?.command | test("\\.claude/hooks/sdd") | not)] |
      .hooks.Stop = [.hooks.Stop[]? | select(.hooks[]?.command | test("\\.claude/hooks/sdd") | not)] |
      if (.hooks.PreToolUse | length) == 0 then del(.hooks.PreToolUse) else . end |
      if (.hooks.PostToolUse | length) == 0 then del(.hooks.PostToolUse) else . end |
      if (.hooks.SessionStart | length) == 0 then del(.hooks.SessionStart) else . end |
      if (.hooks.Stop | length) == 0 then del(.hooks.Stop) else . end |
      if (.hooks | length) == 0 then del(.hooks) else . end
    ' "$settings" > "$tmp" && mv "$tmp" "$settings"
  fi
}

# --- Bridge files (AGENTS.md, GEMINI.md) ---
install_bridge_files() {
  local target="$PROJECT_ROOT/skill/sdd"
  local bridges_dir="$target/bridges"

  for bridge_name in AGENTS.md GEMINI.md; do
    local tmpl="$bridges_dir/${bridge_name}.tmpl"
    local dest="$PROJECT_ROOT/$bridge_name"

    # Read template content
    local content=""
    if [[ -f "$tmpl" ]]; then
      content=$(<"$tmpl")
    else
      # Fallback: minimal inline content
      content="<!-- SDD:START -->
# SDD — Project Manager
Read skill/sdd/SKILL.md for available commands.
All workflow state is in .sdd/. Never write to .claude/.
<!-- SDD:END -->"
    fi

    if [[ ! -f "$dest" ]]; then
      # Create new file
      echo "$content" > "$dest"
      echo "  - Created $bridge_name"
    elif grep -q "<!-- SDD:START -->" "$dest" 2>/dev/null; then
      # Replace existing SDD section
      local tmp
      tmp=$(mktemp)
      sed '/<!-- SDD:START -->/,/<!-- SDD:END -->/d' "$dest" > "$tmp"
      echo "$content" >> "$tmp"
      mv "$tmp" "$dest"
      echo "  - Updated SDD section in $bridge_name"
    else
      # Append to existing file
      printf '\n%s\n' "$content" >> "$dest"
      echo "  - Appended SDD section to $bridge_name"
    fi
  done
}

remove_bridge_files() {
  for bridge_name in AGENTS.md GEMINI.md; do
    local dest="$PROJECT_ROOT/$bridge_name"
    [[ -f "$dest" ]] || continue

    if grep -q "<!-- SDD:START -->" "$dest" 2>/dev/null; then
      local tmp
      tmp=$(mktemp)
      sed '/<!-- SDD:START -->/,/<!-- SDD:END -->/d' "$dest" > "$tmp"
      # Remove file if empty (only whitespace left)
      if [[ ! -s "$tmp" ]] || [[ -z "$(tr -d '[:space:]' < "$tmp")" ]]; then
        rm -f "$dest" "$tmp"
        echo "  - Removed $bridge_name (was SDD-only)"
      else
        mv "$tmp" "$dest"
        echo "  - Removed SDD section from $bridge_name"
      fi
    fi
  done
}

# --- Settings + hook deployment ---
install_settings() {
  deploy_hooks
  install_hooks
}

# --- Cleanup old format ---
cleanup_old_skills() {
  local found=false
  for d in "$PROJECT_ROOT"/.agent/skills/sdd-*; do
    [[ -d "$d" ]] || continue
    found=true
    rm -rf "$d"
    echo "  - Removed old skill: $(basename "$d")"
  done
  if $found; then
    # Clean up empty .agent/skills/ if we emptied it
    rmdir "$PROJECT_ROOT/.agent/skills" 2>/dev/null || true
    rmdir "$PROJECT_ROOT/.agent" 2>/dev/null || true
  fi
}

# --- Cleanup old .claude/-based SDD tooling ---
cleanup_old_sdd() {
  local claude_dir="$PROJECT_ROOT/.claude"
  [[ -d "$claude_dir" ]] || return 0

  # Tooling dirs to remove (NOT data: prds, epics, context, qa, worktrees, agents)
  local tooling_dirs=(
    commands scripts rules rules-reference
    prompts config tests sync
  )
  local tooling_files=(sdd.config settings.json.example)

  # Find what exists
  local found_dirs=()
  local found_files=()
  for d in "${tooling_dirs[@]}"; do
    [[ -d "$claude_dir/$d" ]] && found_dirs+=("$d")
  done
  for f in "${tooling_files[@]}"; do
    [[ -f "$claude_dir/$f" ]] && found_files+=("$f")
  done

  # Nothing to clean
  [[ ${#found_dirs[@]} -eq 0 && ${#found_files[@]} -eq 0 ]] && return 0

  echo ""
  echo "Detected old SDD tooling in .claude/ (replaced by skill/sdd/):"
  for item in ${found_dirs[@]+"${found_dirs[@]}"}; do echo "  - .claude/$item/"; done
  for item in ${found_files[@]+"${found_files[@]}"}; do echo "  - .claude/$item"; done

  # Show what is preserved
  echo ""
  echo "Will NOT touch:"
  for d in prds epics context qa worktrees agents; do
    [[ -d "$claude_dir/$d" ]] && echo "  - .claude/$d/"
  done
  # Non-SDD slash commands live under .claude/commands/ too (e.g. content/ synced
  # from skills/content-agent/). These are NOT sdd tooling — never wipe them.
  for sub in content content-agent; do
    [[ -d "$claude_dir/commands/$sub" ]] && echo "  - .claude/commands/$sub/ (non-SDD, synced from skills/)"
  done
  for f in settings.local.json settings.json CLAUDE.md; do
    [[ -f "$claude_dir/$f" ]] && echo "  - .claude/$f"
  done

  printf "\n  Remove old tooling? (y/N) "
  read -r confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "  Skipped old tooling cleanup."
    return 0
  fi

  # Remove
  for d in ${found_dirs[@]+"${found_dirs[@]}"}; do
    if [[ "$d" == "commands" ]]; then
      # .claude/commands/ mixes SDD's old command namespaces (pm/, context/, …)
      # with non-SDD slash commands (content/ synced from skills/content-agent/).
      # Remove only SDD-owned children; NEVER blanket-rm the whole dir.
      for sub in "$claude_dir/commands"/* "$claude_dir/commands"/.[!.]*; do
        [[ -e "$sub" ]] || continue
        case "$(basename "$sub")" in
          content|content-agent) ;;      # preserve — non-SDD, regenerable via skills/sync.sh
          *) rm -rf "$sub" ;;
        esac
      done
      rmdir "$claude_dir/commands" 2>/dev/null || true   # drop only if now empty
    else
      rm -rf "$claude_dir/$d"
    fi
  done
  for f in ${found_files[@]+"${found_files[@]}"}; do
    rm -f "$claude_dir/$f"
  done

  echo "  Removed SDD tooling from .claude/ (preserved commands/content/ if present)"

  # Warn about stale hook references (old format: .claude/hooks/foo.sh, not .claude/hooks/sdd/)
  for sf in "$claude_dir/settings.json" "$claude_dir/settings.local.json"; do
    if [[ -f "$sf" ]] && grep -q '\.claude/hooks/[^c]' "$sf" 2>/dev/null; then
      echo ""
      echo "  ⚠️  $(basename "$sf") may have stale hook references."
      echo "     Run with --hooks to install SDD hooks at .claude/hooks/sdd/"
      break
    fi
  done
}

# --- Default config deployment ---
deploy_default_config() {
  local config_dir="$PROJECT_ROOT/.sdd/config"
  local defaults_dir="$PROJECT_ROOT/skill/sdd/config"

  [[ -d "$defaults_dir" ]] || return 0
  mkdir -p "$config_dir"

  # Deploy lifecycle.json from default template (preserve existing)
  local lifecycle_default="$defaults_dir/lifecycle.json.default"
  local lifecycle_target="$config_dir/lifecycle.json"
  if [[ -f "$lifecycle_default" && ! -f "$lifecycle_target" ]]; then
    cp "$lifecycle_default" "$lifecycle_target"
    echo "  - Created .sdd/config/lifecycle.json (default config)"
  elif [[ -f "$lifecycle_default" && -f "$lifecycle_target" ]]; then
    echo "  - .sdd/config/lifecycle.json already exists (preserved)"
  fi
}

# --- Global Memory Agent (opt-in via --with-memory) ---
# Ported faithfully from install/local_install.sh (deprecated). Source of the
# daemon code is the repo's memory-agent/ dir, two levels above skill/sdd/.
GLOBAL_AGENT_DIR="$HOME/.config/sdd/memory-agent"

# Resolve the daemon source dir (repo layout: <repo>/memory-agent).
resolve_source_agent_dir() {
  if [[ -d "$SCRIPT_DIR/../../memory-agent" ]]; then
    SOURCE_AGENT_DIR="$(cd "$SCRIPT_DIR/../../memory-agent" && pwd)"
  else
    SOURCE_AGENT_DIR="$SCRIPT_DIR/../../memory-agent"
  fi
}

# Minimal colored helpers (matching the deprecated installer's UX)
mem_info()  { echo "  ✓ $1"; }
mem_warn()  { echo "  ⚠ $1" >&2; }
mem_error() { echo "  ✗ $1" >&2; }

detect_python() {
    local cmd version major minor
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "${major:-0}" -ge 3 ] && [ "${minor:-0}" -ge 10 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

setup_global_venv() {
    if [ ! -d "$GLOBAL_AGENT_DIR/.venv" ]; then
        echo "  Setting up Python virtual environment..."
        "$PYTHON_CMD" -m venv "$GLOBAL_AGENT_DIR/.venv"
        "$GLOBAL_AGENT_DIR/.venv/bin/pip" install -q -r "$GLOBAL_AGENT_DIR/requirements.txt"
    fi
}

register_project() {
    local STATE_FILE="$HOME/.config/sdd/daemon-state.json"
    local PROJ_ROOT="$PROJECT_ROOT"
    "$PYTHON_CMD" -c "
import json, os
from datetime import datetime
state_file = '$STATE_FILE'
data = {}
if os.path.exists(state_file):
    data = json.load(open(state_file))
projects = data.get('projects', {})
projects['$PROJ_ROOT'] = {
    'name': os.path.basename('$PROJ_ROOT'),
    'registered_at': datetime.utcnow().isoformat() + 'Z',
    'last_activity': datetime.utcnow().isoformat() + 'Z',
    'config': {}
}
data['projects'] = projects
os.makedirs(os.path.dirname(state_file), exist_ok=True)
json.dump(data, open(state_file, 'w'), indent=2)
"
}

generate_rollback() {
    cat > "$HOME/.config/sdd/rollback.sh" << 'ROLLBACK'
#!/bin/bash
# Rollback global Memory Agent to per-project mode
echo "Rolling back global Memory Agent..."

# Stop global daemon
[ -f "$HOME/.config/sdd/memory-agent/.pid" ] && kill $(cat "$HOME/.config/sdd/memory-agent/.pid") 2>/dev/null
rm -f "$HOME/.config/sdd/memory-agent/.pid"

# Restore memory-health.sh backup if exists
if [ -f "$HOME/.config/sdd/memory-health.sh.backup" ]; then
    echo "Restoring memory-health.sh from backup..."
fi

echo "Done. Per-project daemons will resume on next hook trigger."
ROLLBACK
    chmod +x "$HOME/.config/sdd/rollback.sh"
}

install_global_agent() {
    # Skip if source directory missing (e.g. skill-only package).
    if [ ! -d "$SOURCE_AGENT_DIR" ]; then
        mem_warn "memory-agent/ source directory not found at $SOURCE_AGENT_DIR."
        mem_warn "Skipping Memory Agent install (install from a full SDD clone to enable)."
        return 0
    fi

    mkdir -p "$GLOBAL_AGENT_DIR" || {
        mem_error "Cannot create $GLOBAL_AGENT_DIR. Check permissions."
        return 1
    }

    local SOURCE_VERSION="0.0.0"
    [ -f "$SOURCE_AGENT_DIR/VERSION" ] && SOURCE_VERSION=$(cat "$SOURCE_AGENT_DIR/VERSION")

    local INSTALLED_VERSION="0.0.0"
    [ -f "$GLOBAL_AGENT_DIR/VERSION" ] && INSTALLED_VERSION=$(cat "$GLOBAL_AGENT_DIR/VERSION")

    if [ -f "$GLOBAL_AGENT_DIR/agent.py" ]; then
        echo "  Updating Memory Agent: v$INSTALLED_VERSION → v$SOURCE_VERSION"
    else
        echo "  Installing Memory Agent globally..."
    fi

    # Always copy agent files (ensures bug fixes are deployed)
    cp "$SOURCE_AGENT_DIR/agent.py" "$GLOBAL_AGENT_DIR/"
    cp "$SOURCE_AGENT_DIR/sdd-memory" "$GLOBAL_AGENT_DIR/"
    cp "$SOURCE_AGENT_DIR/session-start-global.sh" "$GLOBAL_AGENT_DIR/"
    cp "$SOURCE_AGENT_DIR/requirements.txt" "$GLOBAL_AGENT_DIR/"
    cp "$SOURCE_AGENT_DIR/config-defaults.json" "$GLOBAL_AGENT_DIR/"
    chmod +x "$GLOBAL_AGENT_DIR/sdd-memory" "$GLOBAL_AGENT_DIR/session-start-global.sh"
    echo "$SOURCE_VERSION" > "$GLOBAL_AGENT_DIR/VERSION"

    # Ship the self-contained maintenance tool alongside the daemon (it operates
    # on the global DB; the project skill package does not include memory scripts).
    if [ -f "$SOURCE_AGENT_DIR/../scripts/pm/memory-insights-prune.sh" ]; then
        cp "$SOURCE_AGENT_DIR/../scripts/pm/memory-insights-prune.sh" "$GLOBAL_AGENT_DIR/" 2>/dev/null || true
        chmod +x "$GLOBAL_AGENT_DIR/memory-insights-prune.sh" 2>/dev/null || true
    fi

    # Only rebuild venv when version changes or deps updated
    if [ "$SOURCE_VERSION" != "$INSTALLED_VERSION" ] && [ -d "$GLOBAL_AGENT_DIR/.venv" ]; then
        echo "  Rebuilding venv for new version..."
        rm -rf "$GLOBAL_AGENT_DIR/.venv"
    fi

    setup_global_venv
    register_project
    generate_rollback
    mem_info "Memory Agent ready at $GLOBAL_AGENT_DIR"

    # v1.1.0 fixes the consolidation insight-bloat bug. The daemon migration
    # dedups insight rows on startup, but a pre-bloated DB won't shrink on disk
    # until VACUUM. If the global DB is large, hint the prune tool.
    local GLOBAL_DB="$HOME/.config/sdd/memory.db"
    if [ -f "$GLOBAL_DB" ]; then
        local DB_MB=$(( $(stat -f%z "$GLOBAL_DB" 2>/dev/null || stat -c%s "$GLOBAL_DB" 2>/dev/null || echo 0) / 1024 / 1024 ))
        if [ "$DB_MB" -gt 300 ]; then
            mem_warn "Memory DB is ${DB_MB}MB — if bloated by the pre-1.1.0 consolidation bug, reclaim space with:"
            echo "    bash ~/.config/sdd/memory-agent/memory-insights-prune.sh --yes"
        fi
    fi
}

# Orchestrates the opt-in Memory Agent install. Robust under `set -euo pipefail`:
# every failure is non-fatal so a successful skill install is never aborted.
install_memory_agent() {
    echo ""
    echo "🧬 Installing global Memory Agent (--with-memory)..."
    resolve_source_agent_dir
    if PYTHON_CMD=$(detect_python); then
        install_global_agent || mem_warn "Memory Agent install hit an error — skill install is unaffected."
    else
        mem_warn "Python 3.10+ not found. Skipping Memory Agent install."
        echo "    Install Python 3.10+ and re-run with --with-memory to enable."
    fi
}

# --- Core install ---
do_install() {
  local target="$PROJECT_ROOT/skill/sdd"

  if [[ -d "$target" ]] && ! $UPGRADE; then
    echo "SDD already installed at $target/"
    echo "  Use --upgrade to replace skill files"
    echo "  Use --uninstall to remove"
    exit 0
  fi

  # Guard: prevent installing into self (source == target)
  local resolved_src resolved_target
  resolved_src="$(cd "$SCRIPT_DIR" && pwd)"
  resolved_target="$PROJECT_ROOT/skill/sdd"
  if [[ -d "$resolved_target" ]]; then
    resolved_target="$(cd "$resolved_target" && pwd)"
  fi
  if [[ "$resolved_src" == "$resolved_target" ]]; then
    echo "⚠️  Source and target are the same directory (dev repo detected)."
    echo "  For dev repo setup, create the symlink manually:"
    echo "    mkdir -p .claude/skills && ln -s ../../skill/sdd .claude/skills/sdd"
    exit 1
  fi

  echo "Installing SDD v$VERSION to $PROJECT_ROOT/"

  # Copy skill files
  mkdir -p "$target"
  cp "$SCRIPT_DIR/SKILL.md" "$target/SKILL.md"

  # Copy references
  mkdir -p "$target/references"
  if [[ -d "$SCRIPT_DIR/references" ]]; then
    cp "$SCRIPT_DIR/references/"*.md "$target/references/" 2>/dev/null || true
  fi

  # Copy scripts (recursive — preserves subdirs like scripts/pm/)
  mkdir -p "$target/scripts"
  if [[ -d "$SCRIPT_DIR/scripts" ]]; then
    cp -R "$SCRIPT_DIR/scripts/"* "$target/scripts/" 2>/dev/null || true
    find "$target/scripts" -name '*.sh' -exec chmod +x {} \; 2>/dev/null || true
  fi

  # Copy hooks directory (scripts only, registration is separate)
  mkdir -p "$target/hooks"
  if [[ -d "$SCRIPT_DIR/hooks" ]]; then
    cp "$SCRIPT_DIR/hooks/"*.sh "$target/hooks/" 2>/dev/null || true
    chmod +x "$target/hooks/"*.sh 2>/dev/null || true
  fi

  # Copy rules
  if [[ -d "$SCRIPT_DIR/rules" ]]; then
    mkdir -p "$target/rules"
    cp "$SCRIPT_DIR/rules/"*.md "$target/rules/" 2>/dev/null || true
  fi

  # Copy bridge templates
  if [[ -d "$SCRIPT_DIR/bridges" ]]; then
    mkdir -p "$target/bridges"
    cp "$SCRIPT_DIR/bridges/"*.tmpl "$target/bridges/" 2>/dev/null || true
  fi

  # Copy config defaults
  if [[ -d "$SCRIPT_DIR/config" ]]; then
    mkdir -p "$target/config"
    cp "$SCRIPT_DIR/config/"* "$target/config/" 2>/dev/null || true
  fi

  # Copy install.sh itself
  cp "$SCRIPT_DIR/install.sh" "$target/install.sh"
  chmod +x "$target/install.sh"

  echo "  - Copied skill files to skill/sdd/"

  # Copy agent definitions to .claude/agents/ (required by Claude Code harness)
  # Look in skill package first, then source repo layout
  local agents_src=""
  if [[ -d "$SCRIPT_DIR/agents" ]]; then
    agents_src="$SCRIPT_DIR/agents"
  elif [[ -d "$SCRIPT_DIR/../../agents" ]]; then
    agents_src="$SCRIPT_DIR/../../agents"
  fi
  if [[ -n "$agents_src" ]]; then
    mkdir -p "$PROJECT_ROOT/.claude/agents"
    cp "$agents_src/"*.md "$PROJECT_ROOT/.claude/agents/" 2>/dev/null || true
    # Also copy into skill package for future installs
    if [[ "$agents_src" != "$SCRIPT_DIR/agents" ]]; then
      mkdir -p "$target/agents"
      cp "$agents_src/"*.md "$target/agents/" 2>/dev/null || true
    fi
    echo "  - Copied agent definitions to .claude/agents/"
  fi

  # Create .claude/skills/sdd symlink for Claude Code skill discovery
  mkdir -p "$PROJECT_ROOT/.claude/skills"
  local skill_link="$PROJECT_ROOT/.claude/skills/sdd"
  if [[ -L "$skill_link" ]]; then
    rm "$skill_link"  # refresh stale symlink
  fi
  if [[ ! -e "$skill_link" ]]; then
    ln -s "../../skill/sdd" "$skill_link"
    echo "  - Symlinked .claude/skills/sdd → skill/sdd/"
  fi

  # Cleanup old .agent/skills/sdd-* directories
  cleanup_old_skills

  # Cleanup old .claude/-based SDD tooling
  cleanup_old_sdd

  # Bootstrap .sdd/ via init.sh
  if [[ -x "$target/scripts/init.sh" ]]; then
    (cd "$PROJECT_ROOT" && bash "$target/scripts/init.sh")
  else
    echo "  ⚠️  init.sh not found or not executable — skipping .sdd/ bootstrap"
  fi

  # Deploy default config to .sdd/config/ (preserve existing)
  deploy_default_config

  # Deploy SDD rules to .sdd/rules/
  if [[ -d "$target/rules" ]]; then
    cp "$target/rules/"*.md "$PROJECT_ROOT/.sdd/rules/" 2>/dev/null || true
    echo "  - Deployed rules to .sdd/rules/"
  fi

  # Bridge files for cross-tool support (AGENTS.md, GEMINI.md)
  install_bridge_files

  # settings.local.json — user-local permissions + hooks (always, never overwrites)
  install_settings_local

  # Settings + hooks (shared settings.json, opt-in via --hooks)
  if $HOOKS; then
    install_settings
  fi

  # On upgrade: always deploy hooks (settings.json already references them)
  if $UPGRADE; then
    deploy_hooks
    install_hooks
  fi

  # Global Memory Agent (opt-in). Never aborts a successful skill install.
  if $WITH_MEMORY; then
    install_memory_agent || true
  fi

  echo ""
  echo "✅ SDD v$VERSION installed"
  if $UPGRADE; then
    echo "  - Skill files upgraded (.sdd/ data preserved)"
  fi

  # Discoverability: when memory daemon was NOT requested, point users to it.
  if ! $WITH_MEMORY; then
    echo ""
    echo "💡 Memory Agent (cross-session memory) not installed."
    echo "   Re-run with --with-memory to enable, or:"
    echo "     bash skill/sdd/install.sh --with-memory $PROJECT_ROOT"
  fi

  # Detect existing .claude/ data — auto-migrate on upgrade, hint on fresh install
  if [[ -d "$PROJECT_ROOT/.claude/prds" ]] || [[ -d "$PROJECT_ROOT/.claude/epics" ]]; then
    echo ""
    echo "📦 Detected existing SDD data in .claude/"
    if $UPGRADE; then
      echo "  Running migration preview..."
      echo ""
      (cd "$PROJECT_ROOT" && bash "$target/scripts/migrate.sh" --dry-run) || true
      echo ""
      printf "  Migrate now? (y/N) "
      read -r confirm
      if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        (cd "$PROJECT_ROOT" && bash "$target/scripts/migrate.sh")
      else
        echo "  Skipped. Run manually: bash skill/sdd/scripts/migrate.sh"
      fi
    else
      echo "  Run: bash skill/sdd/scripts/migrate.sh --dry-run"
      echo "  to preview migration to .sdd/"
    fi
  else
    echo "Next: Tell your AI assistant to run 'init' to get started"
  fi
}

# --- Main ---
parse_args "$@"

if $UNINSTALL; then
  do_uninstall
else
  do_install
fi
