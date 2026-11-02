# Daten-Update

Die neue CSV liegt auf Manuels Mac unter `~/Documents/Dashboard/Dashboard Data.csv`.

```bash
tools/update.sh "/pfad/zu/Dashboard Data.csv"   # baut Daten, injiziert, testet (setzt bei Fehler zurück)
git add index.html && git commit -m "Dashboard-Daten bis KWxx aktualisiert" && git push
```

- `build_weekly.py` – CSV mit Spalte `Woche` → `DATA`, `WOW_DATA`
- `build_daily.py` – CSV mit Spalte `Datum` → zusätzlich `DAILY_DATA` (Anomalien-Tab, Wochentags-Baseline, Feiertage/Schulferien aus `holidays.py`)
- `inject.py` – positionsgenaue JSON-Ersetzung in `index.html`
- `test_dashboard.py` – Regressionstests, müssen vor jedem Push grün sein

Zahlen sind im deutschen Format (`.` = Tausender, `,` = Dezimal). `holidays.py` deckt bis Okt. 2026 ab und muss für neue Zeiträume ergänzt werden.
