#!/usr/bin/env bash
# json-or-grep.sh — completion-% gate for epic-merge.
#
# Probes python3+json; on failure falls back to anchored grep.
#
# FALLBACK LIMITATION (R-5): fallback validates completion-% key only —
# malformed JSON not caught. Grep path does NOT detect malformed JSON the
# python path would reject.
# See skill/sdd/references/merge.md §Pre-Merge Gate.
#
# Probe order: python3 -c "import json" (preferred) → anchored grep.
# Stderr grammar (AD-7): merge-gate: fr5-python3-fallback: <msg>
# Emission rule: stderr line ONLY on fallback path (happy-path carve-out per AD-7 / NFR-1).
#
# Usage: bash scripts/pm/json-or-grep.sh <path/to/progress.md> <threshold-int>
# Exit: 0 if completion >= threshold; 1 if below; 2 if parse failure.
#
# Anti-pattern guarded (F-10): never invoke as bare `json-or-grep.sh` on $PATH —
# always via `scripts/pm/json-or-grep.sh` repo-relative absolute path.
# Anti-pattern guarded (F-8): grep MUST anchor on `"completion"[[:space:]]*:` not
# loose `completion` substring. Prevents matching `"completion_count":` or
# `"completion_pct":`.

set -euo pipefail

progress_file="${1:-}"
threshold="${2:-}"

if [ -z "$progress_file" ] || [ -z "$threshold" ]; then
  echo "merge-gate: fr5-python3-fallback: usage: $0 <progress_file> <threshold>" >&2
  exit 2
fi

if [ ! -f "$progress_file" ]; then
  echo "merge-gate: fr5-python3-fallback: progress file not found: $progress_file" >&2
  exit 2
fi

if python3 -c "import json" >/dev/null 2>&1; then
  # Happy path — python3 JSON parse. No stderr emission (NFR-1 byte-identity).
  completion=$(python3 -c "import json,sys
try:
  d=json.load(open('$progress_file'))
  print(d.get('completion',''))
except Exception:
  sys.exit(3)
" 2>/dev/null) || {
    echo "merge-gate: fr5-python3-fallback: python3 failed to parse JSON in $progress_file" >&2
    exit 2
  }
else
  # Fallback path — anchored grep on exact `"completion"` key.
  echo "merge-gate: fr5-python3-fallback: python3 unavailable, using grep fallback (no JSON schema validation)" >&2
  completion=$(grep -E '"completion"[[:space:]]*:[[:space:]]*[0-9]+' "$progress_file" | grep -oE '[0-9]+' | head -1)
fi

if [ -z "$completion" ]; then
  echo "merge-gate: fr5-python3-fallback: could not parse completion from $progress_file" >&2
  exit 2
fi

# Integer comparison — fail if not numeric.
case "$completion" in
  ''|*[!0-9]*)
    echo "merge-gate: fr5-python3-fallback: non-numeric completion value '$completion' in $progress_file" >&2
    exit 2
    ;;
esac

if [ "$completion" -ge "$threshold" ]; then
  exit 0
else
  exit 1
fi
