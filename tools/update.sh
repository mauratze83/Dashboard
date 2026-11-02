#!/usr/bin/env bash
# Update index.html from a Composer CSV export, then run the regression tests.
# Usage: tools/update.sh "<path/to/Dashboard Data.csv>"
#
# - Weekly CSV (column "Woche"): updates DATA + WOW_DATA; DAILY_DATA (Anomalien tab) is kept.
# - Daily CSV (column "Datum"): aggregates to ISO weeks AND rebuilds DAILY_DATA.
# Does NOT commit or push — review the test result first.
set -euo pipefail
CSV="$1"
DIR="$(cd "$(dirname "$0")" && pwd)"
HTML="$DIR/../index.html"
WORK="$(mktemp -d)"

HEADER="$(head -1 "$CSV")"
if [[ "$HEADER" == *'"Datum"'* ]]; then
  echo "Format: Tagesdaten"
  python3 "$DIR/build_daily.py" "$CSV" "$WORK"
elif [[ "$HEADER" == *'"Woche"'* ]]; then
  echo "Format: Wochendaten"
  python3 "$DIR/build_weekly.py" "$CSV" "$WORK"
else
  echo "Unbekanntes CSV-Format: $HEADER" >&2; exit 1
fi

cp "$HTML" "$WORK/index.backup.html"
python3 "$DIR/inject.py" "$HTML" "$WORK"
if ! python3 "$DIR/test_dashboard.py" "$HTML" > "$WORK/test.log" 2>&1; then
  grep -E "FAIL|RESULT" "$WORK/test.log" >&2
  cp "$WORK/index.backup.html" "$HTML"
  echo "Tests fehlgeschlagen — index.html wurde zurückgesetzt." >&2
  exit 1
fi
grep RESULT "$WORK/test.log"
