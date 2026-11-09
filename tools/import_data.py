"""Import a Composer CSV export (weekly "Woche" or daily "Datum") into the data store.

Usage:
  python3 import_data.py <export.csv> [--data-dir DIR] [--today YYYY-MM-DD] [--dry-run]

The data store (data/weekly.csv, data/daily.csv) is the single source of truth. An export only needs
to contain the missing period: its periods are added, and periods that already exist in the store are
OVERWRITTEN completely (all channels/intents of that week/day are replaced, so stale rows can't survive).

Checks (ERROR = nothing is written, exit code 1; WARN = imported, but reported):
  ERROR  unknown format / missing columns
  ERROR  checksum: rows don't add up to the export's own total line (file truncated/corrupt)
  ERROR  duplicate rows (same period + channel + intent twice)
  ERROR  dates in the future, or a week that hasn't ended yet
  ERROR  gap in the weekly time series after the merge (e.g. KW44 -> KW46)
  ERROR  daily export with an incomplete week that is not yet in the store (would create a partial week)
  WARN   overwritten periods (old vs. new totals are listed)
  WARN   gaps in the daily series (Anomalien tab) — weekly views are unaffected
  WARN   implausible week: Involved deviates > 35 % or CR > 8 PP from the median of the 4 previous weeks
  WARN   noticeably fewer intents/channels than the previous week
"""
import argparse, csv, os, statistics, sys
from collections import defaultdict
from datetime import date, datetime, timedelta

COLS = ['Kanal', 'Markt', 'Intent', '#Involved', '#Contained', '%CR', '€CS']


def parse_de_num(s):
    s = (s or '').strip().replace('%', '')
    if not s:
        return 0.0
    return float(s.replace('.', '').replace(',', '.'))


def fmt_cs(x):
    return f'{x:.2f}'.replace('.', ',')


def iso_week(d):
    y, w, _ = d.isocalendar()
    return f'{y}-{w:02d}'


def week_monday(label):
    y, w = map(int, label.split('-'))
    return date.fromisocalendar(y, w, 1)


KNOWN_CHANNELS = {'ABC', 'Appchat', 'SMS', 'Webchat', 'WhatsApp'}
INT_RE = r'^\d{1,3}(\.\d{3})*$'                    # 1.491 / 98.526 (German thousands separator)
DEC_RE = r'^\d{1,3}(\.\d{3})*(,\d{1,2})?$'         # 142.708,72 / 329,13 / 196.157,4
PCT_RE = r'^\d{1,3},\d%$'                          # 87,8%


def read_export(path):
    """Return (kind, rows, total, dups, struct_errors).
    kind 'weekly'|'daily'; rows: {(period, ch, intent): [inv, con, cs]}.
    struct_errors: deviations from the usual Composer export structure (each one blocks the import)."""
    import re
    se = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        fields = r.fieldnames or []
        if fields and fields[0] == 'Datum':
            kind, pcol = 'daily', 'Datum'
        elif fields and fields[0] == 'Woche':
            kind, pcol = 'weekly', 'Woche'
        else:
            raise SystemExit(f'ERROR  Unbekannte Datenstruktur: erste Spalte muss "Datum" oder "Woche" sein, ist {fields[:1]}')
        expected = [pcol] + COLS
        if fields != expected:
            raise SystemExit('ERROR  Spalten weichen von der gewohnten Struktur ab.\n'
                             f'       erwartet: {expected}\n       erhalten: {fields}')
        rows, dups, total = {}, [], None
        bad = defaultdict(list)  # problem -> sample line numbers
        for ln, row in enumerate(r, start=2):
            if None in row or any(v is None for v in row.values()):
                bad['falsche Anzahl Felder in der Zeile'].append(ln); continue
            p = row[pcol].strip()
            raw_inv, raw_con, raw_cr, raw_cs = (row[c].strip() for c in ('#Involved', '#Contained', '%CR', '€CS'))
            if not re.match(INT_RE, raw_inv) or not re.match(INT_RE, raw_con):
                bad['#Involved/#Contained nicht im Zahlenformat 1.234'].append(ln)
            if raw_cs and not re.match(DEC_RE, raw_cs):
                bad['€CS nicht im Zahlenformat 1.234,56'].append(ln)
            if not re.match(PCT_RE, raw_cr):
                bad['%CR nicht im Format 12,3%'].append(ln)
            try:
                vals = [parse_de_num(raw_inv), parse_de_num(raw_con), parse_de_num(raw_cs)]
            except ValueError:
                bad['Zahl nicht lesbar'].append(ln); continue
            if not p:  # export's own total line
                total = vals
                continue
            try:
                if kind == 'daily':
                    datetime.strptime(p, '%Y-%m-%d')
                else:
                    if not re.match(r'^\d{4}-\d{2}$', p):
                        raise ValueError
                    week_monday(p)
            except ValueError:
                bad[f'{pcol} nicht im Format ' + ('JJJJ-MM-TT' if kind == 'daily' else 'JJJJ-WW')].append(ln); continue
            ch, it = row['Kanal'].strip(), row['Intent'].strip()
            if not ch or not it:
                bad['Kanal oder Intent leer'].append(ln)
            if row['Markt'].strip() != 'kumuliert':
                bad['Markt ist nicht "kumuliert"'].append(ln)
            inv, con = int(round(vals[0])), int(round(vals[1]))
            if con > inv:
                bad['Contained größer als Involved'].append(ln)
            if inv and re.match(PCT_RE, raw_cr) and abs(parse_de_num(raw_cr) - con / inv * 100) > 0.15:
                bad['%CR passt nicht zu Contained/Involved'].append(ln)
            key = (p, ch, it)
            if key in rows:
                dups.append(key)
            rows[key] = [inv, con, vals[2]]
        for problem, lines in bad.items():
            se.append(f'{problem}: {len(lines)} Zeile(n), z.B. Zeile {", ".join(map(str, lines[:3]))}')
        unknown_ch = {k[1] for k in rows} - KNOWN_CHANNELS
        if unknown_ch:
            se.append(f'Unbekannte Kanäle: {", ".join(sorted(unknown_ch))} (bekannt: {", ".join(sorted(KNOWN_CHANNELS))})')
    return kind, rows, total, dups, se


def read_store(path, pcol):
    rows = {}
    if os.path.exists(path):
        with open(path, encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                rows[(row[pcol], row['Kanal'], row['Intent'])] = [
                    int(row['#Involved']), int(row['#Contained']), parse_de_num(row['€CS'])]
    return rows


def write_store(path, pcol, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow([pcol] + COLS)
        for (p, ch, it) in sorted(rows):
            inv, con, cs = rows[(p, ch, it)]
            cr = f'{con / inv * 100:.1f}'.replace('.', ',') + '%' if inv else '0,0%'
            w.writerow([p, ch, 'kumuliert', it, inv, con, cr, fmt_cs(cs)])
    os.replace(tmp, path)


def totals_by_period(rows):
    t = defaultdict(lambda: [0, 0, 0.0])
    for (p, _, _), v in rows.items():
        t[p][0] += v[0]; t[p][1] += v[1]; t[p][2] += v[2]
    return t


def cr(inv, con):
    return con / inv * 100 if inv else 0.0


def de(x, dec=0):
    """German number formatting for messages: 137108 -> 137.108, 67.7 -> 67,7"""
    return f'{x:,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    ap.add_argument('--today', default=date.today().isoformat())
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    today = date.fromisoformat(a.today)
    errors, warns, infos = [], [], []

    kind, new, total, dups, struct_errors = read_export(a.csv)
    if not new:
        raise SystemExit('ERROR  Die Datei enthält keine Datenzeilen.')
    errors += ['Datenstruktur: ' + m for m in struct_errors]
    if not struct_errors:
        infos.append('Datenstruktur wie gewohnt (Spalten, Zahlenformate, Kanäle, Wertebereiche)')
    if dups:
        errors.append(f'{len(dups)} doppelte Zeilen (gleicher Zeitraum + Kanal + Intent), z.B. {dups[0]}')
    s = [sum(v[i] for v in new.values()) for i in range(3)]
    if total is None:
        warns.append('Keine Summenzeile in der Datei – Vollständigkeit konnte nicht per Prüfsumme geprüft werden.')
    elif round(s[0]) != round(total[0]) or round(s[1]) != round(total[1]) or abs(s[2] - total[2]) > 1.0:
        errors.append(f'Prüfsumme stimmt nicht: Zeilen ergeben Involved {de(s[0])} / Contained {de(s[1])} / '
                      f'CS {de(s[2], 2)}, Summenzeile sagt {de(total[0])} / {de(total[1])} / {de(total[2], 2)} '
                      f'– Datei vermutlich unvollständig.')

    weekly_path = os.path.join(a.data_dir, 'weekly.csv')
    daily_path = os.path.join(a.data_dir, 'daily.csv')
    weekly = read_store(weekly_path, 'Woche')
    daily = read_store(daily_path, 'Datum')
    old_weekly_tot = totals_by_period(weekly)
    if weekly:
        known_intents = {k[2] for k in weekly}
        recent = sorted({k[0] for k in weekly}, key=week_monday)[-4:]
        recent_intents = {k[2] for k in weekly if k[0] in recent}
        new_intents = {k[2] for k in new} - known_intents
        gone_intents = recent_intents - {k[2] for k in new}
        if new_intents:
            warns.append(f'Neue Intents, die es bisher nicht gab: {", ".join(sorted(new_intents))}')
        if gone_intents:
            warns.append(f'Intents aus den letzten 4 Wochen fehlen in der Datei: {", ".join(sorted(gone_intents))}')

    # ---- derive the weekly rows this import contributes
    if kind == 'daily':
        days = sorted({k[0] for k in new})
        future = [d for d in days if date.fromisoformat(d) >= today]
        if future:
            errors.append(f'{len(future)} Tag(e) liegen nicht in der Vergangenheit ({future[0]} bis {future[-1]}) – '
                          f'bitte nur abgeschlossene Tage exportieren.')
        infos.append(f'Format: Tagesdaten, {len(days)} Tage ({days[0]} bis {days[-1]})')
        # merged daily store decides which weeks are complete
        merged_daily = {k: v for k, v in daily.items() if k[0] not in set(days)}
        merged_daily.update(new)
        days_per_week = defaultdict(set)
        for (d, _, _) in merged_daily:
            days_per_week[iso_week(date.fromisoformat(d))].add(d)
        new_weekly = defaultdict(lambda: [0, 0, 0.0])
        touched_weeks = sorted({iso_week(date.fromisoformat(d)) for d in days})
        weeks_to_write = []
        for wk in touched_weeks:
            n = len(days_per_week[wk])
            if n == 7:
                weeks_to_write.append(wk)
            elif week_monday(wk) + timedelta(days=6) >= today:
                errors.append(f'KW {wk} ist noch nicht vorbei ({n}/7 Tage) – bitte erst nach Wochenende importieren.')
            else:
                errors.append(f'KW {wk} unvollständig: nur {n}/7 Tage vorhanden. Bitte die ganze Woche exportieren.')
        for (d, ch, it), v in merged_daily.items():
            wk = iso_week(date.fromisoformat(d))
            if wk in weeks_to_write:
                acc = new_weekly[(wk, ch, it)]
                acc[0] += v[0]; acc[1] += v[1]; acc[2] += v[2]
        new_weekly = {k: [v[0], v[1], round(v[2], 2)] for k, v in new_weekly.items()}
    else:
        weeks_to_write = sorted({k[0] for k in new})
        infos.append(f'Format: Wochendaten, {len(weeks_to_write)} Woche(n) ({weeks_to_write[0]} bis {weeks_to_write[-1]})')
        for wk in weeks_to_write:
            if week_monday(wk) + timedelta(days=6) >= today:
                errors.append(f'KW {wk} ist noch nicht vorbei – bitte erst nach Wochenende importieren.')
        new_weekly = new
        merged_daily = daily

    # ---- merge weekly: replace whole weeks
    merged_weekly = {k: v for k, v in weekly.items() if k[0] not in set(weeks_to_write)}
    merged_weekly.update(new_weekly)
    new_tot = totals_by_period(new_weekly)
    for wk in weeks_to_write:
        if wk in old_weekly_tot:
            o, n = old_weekly_tot[wk], new_tot[wk]
            same = o[0] == n[0] and o[1] == n[1] and abs(o[2] - n[2]) < 0.5
            warns.append(f'KW {wk} war schon vorhanden und wird überschrieben'
                         + (' (Werte identisch).' if same else
                            f': Involved {de(o[0])} → {de(n[0])}, Contained {de(o[1])} → {de(n[1])}, '
                            f'CR {de(cr(o[0], o[1]), 1)} % → {de(cr(n[0], n[1]), 1)} %.'))
        else:
            n = new_tot[wk]
            infos.append(f'KW {wk} neu: Involved {de(n[0])}, Contained {de(n[1])}, CR {de(cr(n[0], n[1]), 1)} %, '
                         f'CS {de(n[2], 2)} €')

    # ---- time-series checks on the merged weekly store
    all_weeks = sorted({k[0] for k in merged_weekly}, key=week_monday)
    gaps = []
    for prev, cur in zip(all_weeks, all_weeks[1:]):
        m = week_monday(prev) + timedelta(days=7)
        while m < week_monday(cur):
            gaps.append(iso_week(m)); m += timedelta(days=7)
    if gaps:
        errors.append(f'Lücke in der Wochenreihe: es fehlen {", ".join("KW " + g for g in gaps)}. '
                      f'Bitte den fehlenden Zeitraum mit exportieren.')
    else:
        infos.append(f'Zeitreihe lückenlos: KW {all_weeks[0]} bis KW {all_weeks[-1]} ({len(all_weeks)} Wochen)')

    # ---- plausibility of each written week vs. the 4 weeks before it
    mt = totals_by_period(merged_weekly)
    for wk in weeks_to_write:
        i = all_weeks.index(wk)
        ref = all_weeks[max(0, i - 4):i]
        if len(ref) >= 2:
            med_inv = statistics.median(mt[r][0] for r in ref)
            med_cr = statistics.median(cr(*mt[r][:2]) for r in ref)
            dev = (mt[wk][0] - med_inv) / med_inv * 100 if med_inv else 0
            dcr = cr(*mt[wk][:2]) - med_cr
            if abs(dev) > 35:
                warns.append(f'KW {wk}: Involved weicht {dev:+.0f} % vom Median der Vorwochen ab – bitte prüfen.')
            if abs(dcr) > 8:
                warns.append(f'KW {wk}: CR weicht {dcr:+.1f} PP vom Median der Vorwochen ab – bitte prüfen.')
        if i > 0:
            pw = all_weeks[i - 1]
            ints = lambda w: {k[2] for k in merged_weekly if k[0] == w}
            chs = lambda w: {k[1] for k in merged_weekly if k[0] == w}
            if len(ints(wk)) < 0.85 * len(ints(pw)):
                warns.append(f'KW {wk}: nur {len(ints(wk))} Intents (Vorwoche {len(ints(pw))}) – Export unvollständig?')
            missing_ch = chs(pw) - chs(wk)
            if missing_ch:
                warns.append(f'KW {wk}: Kanäle fehlen gegenüber Vorwoche: {", ".join(sorted(missing_ch))}')

    # ---- daily series gaps (Anomalien tab only)
    if kind == 'daily' and merged_daily:
        ds = sorted({date.fromisoformat(k[0]) for k in merged_daily})
        dgaps = []
        for p, c in zip(ds, ds[1:]):
            if (c - p).days > 1:
                dgaps.append(f'{(p + timedelta(days=1)).strftime("%d.%m.")}–{(c - timedelta(days=1)).strftime("%d.%m.%Y")}')
        if dgaps:
            warns.append(f'Tagesdaten fehlen für {", ".join(dgaps)} – betrifft nur den Anomalien-Tab, '
                         f'Wochenansichten sind vollständig. Bei Bedarf Tagesexport für diesen Zeitraum nachreichen.')

    for m in infos:
        print('INFO  ', m)
    for m in warns:
        print('WARN  ', m)
    for m in errors:
        print('ERROR ', m)
    if errors:
        print('ABBRUCH: nichts importiert.')
        sys.exit(1)
    if a.dry_run:
        print('Dry-Run: nichts geschrieben.')
        return
    write_store(weekly_path, 'Woche', merged_weekly)
    if kind == 'daily':
        write_store(daily_path, 'Datum', merged_daily)
    print('OK: Datenbestand aktualisiert.')


if __name__ == '__main__':
    main()
