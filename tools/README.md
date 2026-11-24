# Daten-Update

Neue Exporte legt Manuel auf seinem Mac unter `~/Documents/Dashboard/` ab. Ein Export muss **nur den fehlenden
Zeitraum** enthalten. Bevorzugt: **Tagesexport mit Markt** (Spalte `Markt` = Mobilfunk, Dsl, Kabel, Unity, Callya, Fusionc, …).

```bash
tools/update.sh "/pfad/zum/export.csv"            # prüfen, in data/ übernehmen, Dashboard bauen, testen
tools/update.sh "/pfad/zum/export.csv" --dry-run  # nur prüfen, nichts schreiben
git add index.html data && git commit -m "Dashboard-Daten bis KWxx aktualisiert" && git push
```

## Datenbestand (`data/`)
- `daily/JJJJ-MM.csv` – Tagesdaten je Monat (Datum, Kanal, Markt, Intent); Basis für Anomalien
- `weekly.csv` – Wochendaten (Woche, Kanal, Markt, Intent); Basis für alle Wochen-Tabs und die Marktauswertung

Ein Import ergänzt neue Zeiträume und **überschreibt** vorhandene Wochen bzw. Tage vollständig. Bei Tagesexporten
wird jede vollständige Woche zusätzlich in `weekly.csv` übernommen. Alte Exporte ohne Marktaufteilung
(`Markt` = „kumuliert“) werden noch angenommen, fehlen dann aber in den Marktauswertungen (Warnung beim Import).

## Prüfungen (`tools/import_data.py`)
Abbruch ohne Änderung bei: abweichender Spaltenstruktur, falschem Zahlen- oder Datumsformat, unbekanntem Kanal,
Contained > Involved, %CR passt nicht zu Contained/Involved, Prüfsumme gegen die Summenzeile stimmt nicht,
doppelten Zeilen, Tagen, die noch nicht vorbei sind, unvollständiger Woche, Lücke in der Wochenreihe.
Hinweis (Import läuft trotzdem) bei: überschriebenen Wochen (Alt/Neu-Vergleich), neuen oder fehlenden Intents,
fehlenden Kanälen, neuen Marktbezeichnungen, fehlenden Hauptmärkten, auffälliger Abweichung vom Median der Vorwochen,
Lücken in den Tagesdaten. Jeder Import zeigt die Marktanteile der Datei.

## Skripte
- `build_weekly.py` / `build_daily.py` – Bestand → `DATA`, `WOW_DATA` / `DAILY_DATA`
- `build_facts.py` – `weekly.csv` → `FACTS` (Woche × Kanal × Markt × Intent) für Märkte-Tab und Marktfilter
- `merge_daily_markets.py` – hängt die je Markt berechneten Tagesanomalien an `DAILY_DATA` (`by_market`); `update.sh` ruft dafür `build_daily.py` je Hauptmarkt mit `MARKET_FILTER=<Markt>` auf
- `inject.py` – positionsgenaue JSON-Ersetzung in `index.html`
- `test_dashboard.py` – Regressionstests; schlägt einer fehl, setzt `update.sh` Dashboard und Bestand zurück
- `holidays.py` – Feiertage und Schulferien für die Anomalien, gepflegt bis Ostern 2027

## Marktfilter im Dashboard
Der Filter „Markt“ in der Zeitleiste rechnet alle Tabs im Browser aus `FACTS` auf einen Markt um (nur Webchat, Appchat,
WhatsApp). „Alle Märkte“ zeigt die eingebetteten Originaldaten. Nach einem CSV-Upload direkt im Browser ist der
Marktfilter deaktiviert, weil `FACTS` dann nicht mehr zu den Daten passt.
