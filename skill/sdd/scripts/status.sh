#!/usr/bin/env bash
set -euo pipefail

SDD_ROOT="${SDD_ROOT:-.sdd}"

if [ ! -d "$SDD_ROOT" ]; then
  echo "No SDD data yet. Run init to get started."
  exit 0
fi

echo "Project Status"
echo "=============="
echo ""

# PRDs
echo "PRDs:"
if [ -d "$SDD_ROOT/prds" ]; then
  total=$(find "$SDD_ROOT/prds" -maxdepth 1 -name "*.md" ! -name ".*" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$total" -gt 0 ]; then
    backlog=0; in_progress=0; complete=0
    for f in "$SDD_ROOT"/prds/*.md; do
      [ -f "$f" ] || continue
      s=$(grep -m1 '^status:' "$f" 2>/dev/null | sed 's/^status: *//' | tr -d ' ')
      case "$s" in
        backlog)     backlog=$((backlog + 1)) ;;
        in-progress) in_progress=$((in_progress + 1)) ;;
        complete)    complete=$((complete + 1)) ;;
      esac
    done
    echo "  Total: $total (backlog: $backlog, in-progress: $in_progress, complete: $complete)"
  else
    echo "  None"
  fi
else
  echo "  None"
fi

echo ""

# Epics
echo "Epics:"
if [ -d "$SDD_ROOT/epics" ]; then
  epic_count=0; ep_backlog=0; ep_in_progress=0; ep_completed=0
  for epic_dir in "$SDD_ROOT"/epics/*/; do
    [ -d "$epic_dir" ] || continue
    [ -f "$epic_dir/epic.md" ] || continue
    epic_count=$((epic_count + 1))
    s=$(grep -m1 '^status:' "$epic_dir/epic.md" 2>/dev/null | sed 's/^status: *//' | tr -d ' ')
    case "$s" in
      backlog)     ep_backlog=$((ep_backlog + 1)) ;;
      in-progress) ep_in_progress=$((ep_in_progress + 1)) ;;
      completed)   ep_completed=$((ep_completed + 1)) ;;
    esac
  done
  if [ "$epic_count" -gt 0 ]; then
    echo "  Total: $epic_count (backlog: $ep_backlog, in-progress: $ep_in_progress, completed: $ep_completed)"
  else
    echo "  None"
  fi
else
  echo "  None"
fi

echo ""

# Tasks
echo "Tasks:"
if [ -d "$SDD_ROOT/epics" ]; then
  t_total=0; t_open=0; t_in_progress=0; t_closed=0
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    t_total=$((t_total + 1))
    s=$(grep -m1 '^status:' "$f" 2>/dev/null | sed 's/^status: *//' | tr -d ' ')
    case "$s" in
      open)        t_open=$((t_open + 1)) ;;
      in-progress) t_in_progress=$((t_in_progress + 1)) ;;
      closed)      t_closed=$((t_closed + 1)) ;;
    esac
  done < <(find "$SDD_ROOT/epics" -name "[0-9]*.md" 2>/dev/null)
  if [ "$t_total" -gt 0 ]; then
    echo "  Total: $t_total (open: $t_open, in-progress: $t_in_progress, closed: $t_closed)"
  else
    echo "  None"
  fi
else
  echo "  None"
fi

echo ""

# Recent activity
echo "Recent Activity:"
recent=$(find "$SDD_ROOT" -name "*.md" -newer "$SDD_ROOT" -type f 2>/dev/null | head -5)
if [ -n "$recent" ]; then
  echo "$recent" | while read -r f; do
    echo "  $(basename "$f")"
  done
else
  echo "  No recent changes"
fi

exit 0
