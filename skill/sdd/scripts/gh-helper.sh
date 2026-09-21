#!/usr/bin/env bash
# GitHub helper functions for SDD skill.
# Usage:
#   source skill/sdd/scripts/gh-helper.sh
#   check_remote_origin
#   REPO=$(get_repo)
#
# Or run directly:
#   bash skill/sdd/scripts/gh-helper.sh <command> [args...]
#
# Commands:
#   check-remote          - Block writes to template repo
#   get-repo              - Print OWNER/REPO from git remote
#   strip-frontmatter     - Remove YAML frontmatter from file

set -euo pipefail

SDD_ROOT="${SDD_ROOT:-.sdd}"

# Detect gh CLI availability
if command -v gh >/dev/null 2>&1; then
  GH_AVAILABLE=1
else
  GH_AVAILABLE=0
fi
export GH_AVAILABLE

# Block writes to the SDD template repo. Exits 1 if matched.
check_remote_origin() {
  local remote_url
  remote_url=$(git remote get-url origin 2>/dev/null || echo "")
  if [[ "$remote_url" == *"automazeio/ccpm"* ]]; then
    echo "Cannot modify template repo. Run: git remote set-url origin YOUR_REPO_URL" >&2
    return 1
  fi
  if [ -z "$remote_url" ]; then
    echo "No git remote origin found." >&2
    return 1
  fi
}

# Print OWNER/REPO from git remote origin.
get_repo() {
  local remote_url repo
  remote_url=$(git remote get-url origin 2>/dev/null || echo "")
  repo=$(echo "$remote_url" | sed 's|.*github.com[:/]||' | sed 's|\.git$||')
  if [ -z "$repo" ]; then
    echo "Cannot detect GitHub repo from remote origin." >&2
    return 1
  fi
  echo "$repo"
}

# Strip YAML frontmatter from a markdown file.
# Usage: strip_frontmatter input.md [output.md]
strip_frontmatter() {
  local input="${1:?Usage: strip_frontmatter input.md [output.md]}"
  local output="${2:-}"
  if [ -n "$output" ]; then
    sed '1,/^---$/d; 1,/^---$/d' "$input" > "$output"
  else
    sed '1,/^---$/d; 1,/^---$/d' "$input"
  fi
}

# Run gh if available, otherwise create local file with sync-later note.
# Usage: gh_or_local <gh_args...>
# On fallback, writes to $SDD_ROOT/context/pending-sync.md
gh_or_local() {
  if [ "$GH_AVAILABLE" -eq 1 ]; then
    gh "$@"
  else
    local action="${1:-unknown}"
    local pending_file="$SDD_ROOT/context/pending-sync.md"
    mkdir -p "$(dirname "$pending_file")"
    echo "- $(date -u +"%Y-%m-%dT%H:%M:%SZ") gh $*" >> "$pending_file"
    echo "gh not available. Logged to $pending_file for later sync." >&2
    return 0
  fi
}

# CLI interface - run commands directly
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  cmd="${1:-}"
  shift 2>/dev/null || true
  case "$cmd" in
    check-remote)       check_remote_origin ;;
    get-repo)           get_repo ;;
    strip-frontmatter)  strip_frontmatter "$@" ;;
    *)
      echo "Usage: $0 <check-remote|get-repo|strip-frontmatter> [args...]"
      exit 1
      ;;
  esac
fi
