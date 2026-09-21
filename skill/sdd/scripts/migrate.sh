#!/usr/bin/env bash
set -euo pipefail

# Migration script: copy .claude/ data to .sdd/
# Copy-not-move, idempotent, never overwrites user edits in .sdd/

CLAUDE_ROOT="${CLAUDE_ROOT:-.claude}"
SDD_ROOT="${SDD_ROOT:-.sdd}"
DRY_RUN=false
FORCE=false

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --force)   FORCE=true ;;
    --help|-h)
      echo "Usage: migrate.sh [--dry-run] [--force]"
      echo ""
      echo "Copies data from $CLAUDE_ROOT/ to $SDD_ROOT/ preserving directory structure."
      echo "Originals in $CLAUDE_ROOT/ are never deleted."
      echo ""
      echo "Flags:"
      echo "  --dry-run  Show what would be migrated without copying"
      echo "  --force    Overwrite conflicts (backs up to $SDD_ROOT/.migration-backup/)"
      exit 0
      ;;
  esac
done

# Verify source exists
if [ ! -d "$CLAUDE_ROOT" ]; then
  echo "❌ $CLAUDE_ROOT not found. Nothing to migrate."
  exit 1
fi

# Ensure target structure exists
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/init.sh" ]; then
  "$SCRIPT_DIR/init.sh" > /dev/null 2>&1
else
  echo "❌ init.sh not found at $SCRIPT_DIR/init.sh"
  exit 1
fi

# Directory mapping: source (relative to CLAUDE_ROOT) -> target (relative to SDD_ROOT)
src_dirs=("prds" "epics" "context" "context/verify" "config" "context/sessions" "qa" "context/progress")
dst_dirs=("prds" "epics" "context" "verify"         "config" "sessions"         "qa" "progress")

# Counters
migrated=0
skipped=0
conflicts=0
missing=0

# Track details for report
conflict_files=()
missing_dirs=()

migrate_file() {
  local src="$1"
  local dst="$2"

  if [ ! -f "$dst" ]; then
    if [ "$DRY_RUN" = true ]; then
      echo "  [would migrate] $src -> $dst"
    else
      mkdir -p "$(dirname "$dst")"
      cp -L "$src" "$dst"
    fi
    migrated=$((migrated + 1))
  elif diff -q "$src" "$dst" > /dev/null 2>&1; then
    skipped=$((skipped + 1))
  else
    if [ "$FORCE" = true ]; then
      local backup_dir="$SDD_ROOT/.migration-backup/$(dirname "${dst#"$SDD_ROOT/"}")"
      if [ "$DRY_RUN" = true ]; then
        echo "  [would force overwrite] $dst (backup to $backup_dir/)"
      else
        mkdir -p "$backup_dir"
        cp -L "$dst" "$backup_dir/"
        cp -L "$src" "$dst"
      fi
      migrated=$((migrated + 1))
    else
      conflict_files+=("$src -> $dst")
      conflicts=$((conflicts + 1))
    fi
  fi
}

# Process each directory mapping
for i in "${!src_dirs[@]}"; do
  src_dir="$CLAUDE_ROOT/${src_dirs[$i]}"
  dst_dir="$SDD_ROOT/${dst_dirs[$i]}"

  if [ ! -d "$src_dir" ]; then
    missing_dirs+=("${src_dirs[$i]}")
    missing=$((missing + 1))
    continue
  fi

  # Find all regular files and symlinks (dereferenced via cp -L)
  while IFS= read -r -d '' file; do
    # Compute relative path within source dir
    rel="${file#"$src_dir/"}"
    target="$dst_dir/$rel"
    migrate_file "$file" "$target"
  done < <(find "$src_dir" -type f -print0 -o -type l -print0 2>/dev/null)
done

# Report
echo ""
if [ "$DRY_RUN" = true ]; then
  echo "📊 Migration Report (DRY RUN — no files copied):"
else
  echo "📊 Migration Report:"
fi
echo "  Migrated:  $migrated files"
echo "  Skipped:   $skipped files (already exist, identical)"
echo "  Conflicts: $conflicts files (different content, NOT overwritten)"
echo "  Missing:   $missing source directories"
echo ""
echo "  Source: $CLAUDE_ROOT/"
echo "  Target: $SDD_ROOT/"

if [ ${#conflict_files[@]} -gt 0 ]; then
  echo ""
  echo "⚠️  Conflicting files (not overwritten — use --force to overwrite with backup):"
  for f in "${conflict_files[@]}"; do
    echo "  - $f"
  done
fi

if [ ${#missing_dirs[@]} -gt 0 ]; then
  echo ""
  echo "📭 Missing source directories (skipped):"
  for d in "${missing_dirs[@]}"; do
    echo "  - $CLAUDE_ROOT/$d"
  done
fi

if [ "$migrated" -eq 0 ] && [ "$skipped" -eq 0 ] && [ "$conflicts" -eq 0 ]; then
  echo ""
  echo "Nothing to migrate — no files found in source directories."
fi

if [ "$migrated" -gt 0 ] || [ "$conflicts" -gt 0 ]; then
  echo ""
  echo "Note: Original files in $CLAUDE_ROOT/ are preserved."
  echo "      Path references inside files still point to .claude/ — manual update may be needed."
fi
