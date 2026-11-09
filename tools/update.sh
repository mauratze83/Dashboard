#!/usr/bin/env bash
# Import a Composer export (only the missing period is needed) and rebuild index.html.
# Usage: tools/update.sh "<path/to/export.csv>" [--dry-run]
#
# 1. tools/import_data.py checks structure, checksum, time series, and merges into data/
#    (existing weeks/days are overwritten). Any ERROR aborts before anything is written.
# 2. DATA/WOW_DATA are rebuilt from data/weekly.csv, DAILY_DATA from data/daily.csv.
# 3. Regression tests; on failure index.html AND data/ are restored.
# Does NOT commit or push.
set -euo pipefail
CSV="$1"; shift || true
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$DIR/.."
HTML="$ROOT/index.html"
WORK="$(mktemp -d)"

if [[ "${1:-}" == "--dry-run" ]]; then
  python3 -I "$DIR/import_data.py" "$CSV" --dry-run
  exit 0
fi

cp "$HTML" "$WORK/index.backup.html"
cp -r "$ROOT/data" "$WORK/data.backup"
restore() {
  cp "$WORK/index.backup.html" "$HTML"
  rm -rf "$ROOT/data" && cp -r "$WORK/data.backup" "$ROOT/data"
}

python3 -I "$DIR/import_data.py" "$CSV"

mkdir -p "$WORK/w" "$WORK/d"
python3 "$DIR/build_weekly.py" "$ROOT/data/weekly.csv" "$WORK/w" > "$WORK/build.log"
python3 "$DIR/build_daily.py" "$ROOT/data/daily.csv" "$WORK/d" >> "$WORK/build.log"
cp "$WORK/d/DAILY_DATA.json" "$WORK/w/"
if ! python3 "$DIR/inject.py" "$HTML" "$WORK/w" > "$WORK/inject.log" 2>&1; then
  cat "$WORK/inject.log" >&2; restore; echo "Einbau fehlgeschlagen — alles zurückgesetzt." >&2; exit 1
fi
if ! python3 "$DIR/test_dashboard.py" "$HTML" > "$WORK/test.log" 2>&1; then
  grep -E "FAIL|RESULT" "$WORK/test.log" >&2; restore
  echo "Tests fehlgeschlagen — index.html und data/ wurden zurückgesetzt." >&2; exit 1
fi
grep RESULT "$WORK/test.log"
