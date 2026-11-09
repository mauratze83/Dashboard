# Daten-Update

Neue Exporte legt Manuel auf seinem Mac unter `~/Documents/Dashboard/` ab. Ein Export muss **nur den fehlenden
Zeitraum** enthalten, Wochen- oder Tagesformat.

```bash
tools/update.sh "/pfad/zum/export.csv"            # prüfen, in data/ übernehmen, Dashboard bauen, testen
tools/update.sh "/pfad/zum/export.csv" --dry-run  # nur prüfen, nichts schreiben
git add index.html data && git commit -m "Dashboard-Daten bis KWxx aktualisiert" && git push
```

## Datenbestand (`data/`)
- `weekly.csv` – alle Wochen (Basis für alle Wochen-Tabs und WoW)
- `daily.csv` – alle Tage, die als Tagesexport kamen (Basis für den Anomalien-Tab)

Beide Dateien haben dieselbe Struktur wie die Composer-Exporte. Ein Import ergänzt neue Zeiträume und
**überschreibt** vorhandene Wochen bzw. Tage vollständig. Bei Tagesexporten wird jede vollständige Woche
zusätzlich in `weekly.csv` übernommen.

## Prüfungen (`tools/import_data.py`)
Abbruch ohne Änderung bei: abweichender Spaltenstruktur, falschem Zahlen- oder Datumsformat, unbekanntem Kanal,
Contained > Involved, %CR passt nicht zu Contained/Involved, Prüfsumme gegen die Summenzeile stimmt nicht,
doppelten Zeilen, Tagen, die noch nicht vorbei sind, unvollständiger Woche, Lücke in der Wochenreihe.
Hinweis (Import läuft trotzdem) bei: überschriebenen Wochen (Alt/Neu-Vergleich), neuen oder fehlenden Intents,
fehlenden Kanälen, auffälliger Abweichung vom Median der Vorwochen, Lücken in den Tagesdaten.

## Skripte
- `build_weekly.py` / `build_daily.py` – Bestand → `DATA`, `WOW_DATA` / `DAILY_DATA`
- `inject.py` – positionsgenaue JSON-Ersetzung in `index.html`
- `test_dashboard.py` – Regressionstests; schlägt einer fehl, setzt `update.sh` Dashboard und Bestand zurück
- `holidays.py` – Feiertage und Schulferien für die Anomalien, gepflegt bis Ostern 2027
