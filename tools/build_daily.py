import csv, json, re, statistics, sys, os
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from holidays import day_context

NOISE = {'None','Saleslivechat','Spam','Kein Topintent','Catchphrasedecease',
         'Chatimmobilienwirtschaft','Surveyimmobilienwirtschaft',''}
MAIN_CH = ['Webchat','Appchat','WhatsApp']

def parse_de_num(s):
    """Parse German-formatted number: '.' = thousands sep, ',' = decimal sep."""
    s = (s or '').strip()
    if not s:
        return 0.0
    s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

def iso_week_label(date_str):
    d = datetime.strptime(date_str, '%Y-%m-%d')
    iso_year, iso_week, _ = d.isocalendar()
    return f'{iso_year}-{iso_week:02d}'

path = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else '.'
with open(path, encoding='utf-8-sig') as f:
    r = csv.DictReader(f)
    rows = []
    for row in r:
        d = row['Datum'].strip()
        if not d:
            continue
        inv = int(round(parse_de_num(row['#Involved'])))
        con = int(round(parse_de_num(row['#Contained'])))
        cs = parse_de_num(row['€CS'])
        rows.append({
            'd': d,
            'w': iso_week_label(d),
            'ch': row['Kanal'].strip(),
            'intent': row['Intent'].strip(),
            'inv': inv,
            'con': con,
            'cs': cs
        })

weeks = sorted(set(r['w'] for r in rows))
days = sorted(set(r['d'] for r in rows))
print('weeks:', weeks[0], '..', weeks[-1], 'count', len(weeks))
print('days:', days[0], '..', days[-1], 'count', len(days))

# ============================================================
# WEEKLY AGGREGATION (same logic as before, now derived from daily rows)
# ============================================================

# weekly_totals: FULL unfiltered (all channels, all intents incl noise)
wt_inv = defaultdict(int); wt_con = defaultdict(int); wt_cs = defaultdict(float)
for row in rows:
    wt_inv[row['w']] += row['inv']
    wt_con[row['w']] += row['con']
    wt_cs[row['w']] += row['cs']

weekly_totals = []
for w in weeks:
    inv = wt_inv[w]; con = wt_con[w]; cs = wt_cs[w]
    cr = round(con/inv*100, 1) if inv else 0
    weekly_totals.append({'w': w, 'inv': inv, 'con': con, 'cr': cr, 'cs': round(cs,2)})

clean_rows = [r for r in rows if r['intent'] not in NOISE]

it_inv = defaultdict(int); it_con = defaultdict(int); it_cs = defaultdict(float)
for row in clean_rows:
    it_inv[row['intent']] += row['inv']
    it_con[row['intent']] += row['con']
    it_cs[row['intent']] += row['cs']

intent_totals = []
for intent in it_inv:
    inv = it_inv[intent]; con = it_con[intent]
    cr = round(con/inv*100,1) if inv else 0
    intent_totals.append({'i': intent, 'inv': inv, 'con': con, 'cr': cr, 'cs': round(it_cs[intent],2)})
intent_totals.sort(key=lambda x: (-x['inv'], x['i']))

top10_names = [x['i'] for x in intent_totals[:10]]

iw_inv = defaultdict(lambda: defaultdict(int))
iw_con = defaultdict(lambda: defaultdict(int))
for row in clean_rows:
    iw_inv[row['intent']][row['w']] += row['inv']
    iw_con[row['intent']][row['w']] += row['con']

intent_weekly_cr = {}
for intent in iw_inv:
    arr = []
    for w in weeks:
        inv = iw_inv[intent].get(w,0); con = iw_con[intent].get(w,0)
        cr = round(con/inv*100,1) if inv else None
        arr.append(cr)
    intent_weekly_cr[intent] = arr

channels = MAIN_CH

ch_inv = defaultdict(int); ch_con = defaultdict(int); ch_cs = defaultdict(float)
for row in clean_rows:
    if row['ch'] in MAIN_CH:
        ch_inv[row['ch']] += row['inv']
        ch_con[row['ch']] += row['con']
        ch_cs[row['ch']] += row['cs']

ch_totals = {}
for ch in MAIN_CH:
    inv = ch_inv[ch]; con = ch_con[ch]
    cr = round(con/inv*100,1) if inv else 0
    ch_totals[ch] = {'inv': inv, 'con': con, 'cr': cr, 'cs': round(ch_cs[ch],2)}

wch_inv = defaultdict(lambda: defaultdict(int))
wch_con = defaultdict(lambda: defaultdict(int))
wch_cs = defaultdict(lambda: defaultdict(float))
for row in clean_rows:
    if row['ch'] in MAIN_CH:
        wch_inv[row['ch']][row['w']] += row['inv']
        wch_con[row['ch']][row['w']] += row['con']
        wch_cs[row['ch']][row['w']] += row['cs']

weekly_cr_by_ch = {}
weekly_cs_by_ch = {}
for ch in MAIN_CH:
    crs = []
    css = []
    for w in weeks:
        inv = wch_inv[ch].get(w,0); con = wch_con[ch].get(w,0)
        cr = round(con/inv*100,1) if inv else None
        crs.append(cr)
        css.append(round(wch_cs[ch].get(w,0),2))
    weekly_cr_by_ch[ch] = crs
    weekly_cs_by_ch[ch] = css

DATA = {
    'weeks': weeks,
    'weekly_totals': weekly_totals,
    'intent_totals': intent_totals,
    'intent_weekly_cr': intent_weekly_cr,
    'top10_names': top10_names,
    'channels': channels,
    'ch_totals': ch_totals,
    'weekly_cr_by_ch': weekly_cr_by_ch,
    'weekly_cs_by_ch': weekly_cs_by_ch,
}

# ============================================================
# WOW_DATA (last 2 weeks, same as before)
# ============================================================
last_w = weeks[-1]
prev_w = weeks[-2]

def per_intent_week(w, src_rows):
    inv = defaultdict(int); con = defaultdict(int); cs = defaultdict(float)
    for row in src_rows:
        if row['w'] == w:
            inv[row['intent']] += row['inv']
            con[row['intent']] += row['con']
            cs[row['intent']] += row['cs']
    return inv, con, cs

inv_cur, con_cur, cs_cur = per_intent_week(last_w, clean_rows)
inv_prev, con_prev, cs_prev = per_intent_week(prev_w, clean_rows)

all_intents = set(inv_cur) | set(inv_prev)
wow = []
for intent in all_intents:
    ic = inv_cur.get(intent,0); cc = con_cur.get(intent,0); csc = cs_cur.get(intent,0.0)
    ip = inv_prev.get(intent,0); cp = con_prev.get(intent,0); csp = cs_prev.get(intent,0.0)
    crc = round(cc/ic*100,1) if ic else 0
    crp = round(cp/ip*100,1) if ip else 0
    wow.append({
        'i': intent,
        'inv_cur': ic, 'con_cur': cc, 'cr_cur': crc, 'cs_cur': round(csc,2),
        'inv_prev': ip, 'con_prev': cp, 'cr_prev': crp, 'cs_prev': round(csp,2),
        'cs_delta': round(csc - csp, 2),
        'inv_delta': ic - ip,
        'inv_delta_pct': round((ic - ip) / ip * 100, 1) if ip else 0.0,
        'cr_delta': round(crc - crp, 1),
    })
wow.sort(key=lambda x: (-x['inv_cur'], x['i']))

full_inv_cur = wt_inv[last_w]; full_con_cur = wt_con[last_w]; full_cs_cur = wt_cs[last_w]
full_inv_prev = wt_inv[prev_w]; full_con_prev = wt_con[prev_w]; full_cs_prev = wt_cs[prev_w]

clean_inv_cur_sum = sum(inv_cur.values()); clean_con_cur_sum = sum(con_cur.values()); clean_cs_cur_sum = sum(cs_cur.values())
clean_inv_prev_sum = sum(inv_prev.values()); clean_con_prev_sum = sum(con_prev.values()); clean_cs_prev_sum = sum(cs_prev.values())

rem_inv_cur = full_inv_cur - clean_inv_cur_sum
rem_con_cur = full_con_cur - clean_con_cur_sum
rem_cs_cur = full_cs_cur - clean_cs_cur_sum
rem_inv_prev = full_inv_prev - clean_inv_prev_sum
rem_con_prev = full_con_prev - clean_con_prev_sum
rem_cs_prev = full_cs_prev - clean_cs_prev_sum

rem_cr_cur = round(rem_con_cur/rem_inv_cur*100,1) if rem_inv_cur else 0
rem_cr_prev = round(rem_con_prev/rem_inv_prev*100,1) if rem_inv_prev else 0

wow.append({
    'i': 'Sonstige_ABC_SMS_Noise',
    'inv_cur': rem_inv_cur, 'con_cur': rem_con_cur, 'cr_cur': rem_cr_cur, 'cs_cur': round(rem_cs_cur,2),
    'inv_prev': rem_inv_prev, 'con_prev': rem_con_prev, 'cr_prev': rem_cr_prev, 'cs_prev': round(rem_cs_prev,2),
    'cs_delta': round(rem_cs_cur - rem_cs_prev, 2),
    'inv_delta': rem_inv_cur - rem_inv_prev,
    'inv_delta_pct': round((rem_inv_cur - rem_inv_prev) / rem_inv_prev * 100, 1) if rem_inv_prev else 0.0,
    'cr_delta': round(rem_cr_cur - rem_cr_prev, 1),
})

WOW_DATA = {
    'last': last_w,
    'prev': prev_w,
    'wow': wow,
}

assert sum(x['inv_cur'] for x in wow) == full_inv_cur
assert sum(x['con_cur'] for x in wow) == full_con_cur
assert sum(x['inv_prev'] for x in wow) == full_inv_prev
assert sum(x['con_prev'] for x in wow) == full_con_prev
print('WOW VERIFY OK')
print('Last week', last_w, 'Involved', full_inv_cur, 'Contained', full_con_cur, 'CR', round(full_con_cur/full_inv_cur*100,1), 'CS', round(full_cs_cur,2))
print('Prev week', prev_w, 'Involved', full_inv_prev, 'Contained', full_con_prev)

# ============================================================
# DAILY_DATA — new: for the Anomalien (Tagesbasis) tab
# ============================================================
# Daily totals (full, unfiltered — mirrors weekly_totals logic)
dt_inv = defaultdict(int); dt_con = defaultdict(int); dt_cs = defaultdict(float)
for row in rows:
    dt_inv[row['d']] += row['inv']
    dt_con[row['d']] += row['con']
    dt_cs[row['d']] += row['cs']

daily_totals = []
for d in days:
    inv = dt_inv[d]; con = dt_con[d]; cs = dt_cs[d]
    cr = round(con/inv*100, 1) if inv else 0
    row_out = {'d': d, 'inv': inv, 'con': con, 'cr': cr, 'cs': round(cs,2)}
    ctx = day_context(d)
    if 'holiday' in ctx:
        row_out['holiday'] = ctx['holiday']
    if 'school_holiday' in ctx:
        row_out['school_holiday'] = ctx['school_holiday']
    daily_totals.append(row_out)

# Per-intent daily CR (clean rows only) — needed to flag which intent(s) drove an anomalous day
di_inv = defaultdict(lambda: defaultdict(int))
di_con = defaultdict(lambda: defaultdict(int))
for row in clean_rows:
    di_inv[row['intent']][row['d']] += row['inv']
    di_con[row['intent']][row['d']] += row['con']

# Anomaly detection: rolling baseline (mean + stdev) over the SAME weekday only (e.g. a Monday
# is compared against the last WEEKDAY_WINDOW Mondays, not against a 14-calendar-day window that
# mixes in weekends). Weekday volume/CR behaves structurally differently from weekend volume/CR,
# so mixing them inflates the baseline stdev and produces both false positives and false negatives.
WINDOW = 14             # kept for calendar-day context elsewhere (display only)
WEEKDAY_WINDOW = 6      # how many preceding occurrences of the same weekday to use as baseline
Z_THRESH = 2.0

def rolling_zscores(series_by_day, days_list):
    """series_by_day: dict d -> value. Returns list of (day, value, baseline_mean, baseline_std, zscore),
    where the baseline is computed only from the WEEKDAY_WINDOW preceding days with the SAME
    weekday (Mon vs Mon, Sat vs Sat, etc.), excluding the day itself."""
    out = []
    # index days by weekday (0=Mon..6=Sun) to build same-weekday trailing windows efficiently
    weekday_of = {}
    same_weekday_occurrences = defaultdict(list)  # weekday -> ordered list of day strings seen so far
    for d in days_list:
        wd = datetime.strptime(d, '%Y-%m-%d').weekday()
        weekday_of[d] = wd
    for idx, d in enumerate(days_list):
        wd = weekday_of[d]
        occ = same_weekday_occurrences[wd]
        window_days = occ[-WEEKDAY_WINDOW:]  # last up-to-6 prior occurrences of this weekday
        window_vals = [series_by_day.get(dd, 0) for dd in window_days]
        val = series_by_day.get(d, 0)
        if len(window_vals) < 4:
            out.append({'d': d, 'val': val, 'mean': None, 'std': None, 'z': None})
        else:
            mean = statistics.mean(window_vals)
            std = statistics.pstdev(window_vals)
            z = (val - mean) / std if std > 0 else 0.0
            out.append({'d': d, 'val': val, 'mean': round(mean,2), 'std': round(std,2), 'z': round(z,2)})
        occ.append(d)  # register this day AFTER computing its z-score (trailing, excludes itself)
    return out

inv_series = {d['d']: d['inv'] for d in daily_totals}
cr_series = {d['d']: d['cr'] for d in daily_totals}

inv_z = rolling_zscores(inv_series, days)
cr_z = rolling_zscores(cr_series, days)

anomalies = []
for i, d in enumerate(days):
    iv = inv_z[i]; cv = cr_z[i]
    flags = []
    if iv['z'] is not None and abs(iv['z']) >= Z_THRESH:
        flags.append({'metric': 'inv', 'z': iv['z'], 'val': iv['val'], 'baseline_mean': iv['mean'], 'baseline_std': iv['std']})
    if cv['z'] is not None and abs(cv['z']) >= Z_THRESH:
        flags.append({'metric': 'cr', 'z': cv['z'], 'val': cv['val'], 'baseline_mean': cv['mean'], 'baseline_std': cv['std']})
    if flags:
        # Direction(s) the day's overall metrics actually moved. A driver intent must move the
        # SAME way, otherwise it's not a cause of the flagged anomaly (e.g. showing an intent whose
        # CR collapsed as the "driver" of a day where overall CR spiked up — contradictory).
        cr_flag = next((f for f in flags if f['metric'] == 'cr'), None)
        cr_direction = (1 if cr_flag['val'] > cr_flag['baseline_mean'] else -1) if cr_flag else None
        inv_flag = next((f for f in flags if f['metric'] == 'inv'), None)
        inv_direction = (1 if inv_flag['val'] > inv_flag['baseline_mean'] else -1) if inv_flag else None

        # find top intent contributors for this day (by absolute CR deviation vs that intent's own
        # same-weekday baseline — e.g. a Sunday's intent CR is compared against prior Sundays only,
        # not against a calendar window that mixes in weekdays), restricted to intents whose CR AND
        # volume moved consistently with the flagged direction(s)
        idx_in_days = days.index(d)
        wd_today = datetime.strptime(d, '%Y-%m-%d').weekday()
        same_wd_days = [days[j] for j in range(idx_in_days) if datetime.strptime(days[j], '%Y-%m-%d').weekday() == wd_today]
        same_wd_days = same_wd_days[-WEEKDAY_WINDOW:]
        top_intents = []
        for intent in di_inv:
            day_inv = di_inv[intent].get(d, 0)
            if day_inv < 20:
                continue
            day_con = di_con[intent].get(d, 0)
            day_cr = round(day_con/day_inv*100, 1) if day_inv else 0
            # intent's own trailing baseline CR and volume, same weekday only
            hist_invs = [di_inv[intent].get(dd, 0) for dd in same_wd_days]
            hist_cons = [di_con[intent].get(dd, 0) for dd in same_wd_days]
            hist_inv_sum = sum(hist_invs); hist_con_sum = sum(hist_cons)
            if hist_inv_sum < 50:
                continue
            baseline_cr = hist_con_sum / hist_inv_sum * 100
            dev = day_cr - baseline_cr
            if abs(dev) < 15:
                continue
            # direction check: a CR-flagged day only accepts drivers whose CR deviation has the
            # same sign as the overall CR move (and likewise for volume, using this intent's share
            # of the trailing-baseline daily average vs. its volume today)
            if cr_direction is not None and (dev > 0) != (cr_direction > 0):
                continue
            if inv_direction is not None and cr_direction is None:
                baseline_daily_avg = hist_inv_sum / len(hist_invs) if hist_invs else 0
                vol_dev = day_inv - baseline_daily_avg
                if (vol_dev > 0) != (inv_direction > 0):
                    continue
            top_intents.append({'i': intent, 'inv': day_inv, 'cr': day_cr, 'baseline_cr': round(baseline_cr,1), 'dev': round(dev,1)})
        top_intents.sort(key=lambda x: (-abs(x['dev']), x['i']))

        # Feiertage/Schulferien: bundesweite Feiertage und Zeiten mit vielen gleichzeitigen
        # Schulferien fuehren erfahrungsgemaess zu WENIGER Volumen (negativer Impact auf Involved).
        # Wird als moeglicher Treiber/Kommentar nur ergaenzt, wenn die Richtung passt
        # (Involved-Anomalie nach unten, oder keine Involved-Anomalie aber ein Feiertag/Ferien-Tag,
        # dann rein informativ als Kommentar).
        ctx = day_context(d)
        calendar_note = None
        if ctx.get('holiday'):
            calendar_note = f"Bundesweiter Feiertag: {ctx['holiday']}"
        elif ctx.get('school_holiday'):
            calendar_note = f"Schulferien: {ctx['school_holiday']}"
        if calendar_note:
            entry = {'i': calendar_note, 'inv': None, 'cr': None, 'baseline_cr': None, 'dev': None, 'calendar': True}
            if inv_direction == -1:
                # Volumen ist (wie fuer Feiertage/Ferien typisch) nach UNTEN ausgeschlagen —
                # sehr wahrscheinlicher Treiber, ganz nach vorne stellen.
                top_intents.insert(0, entry)
            else:
                # Entweder keine Involved-Anomalie (z.B. nur CR betroffen), oder Volumen ist
                # AUSNAHMSWEISE nach oben ausgeschlagen (z.B. Rueckkehr-Traffic am Ferienende) —
                # dann nur als informativer Kommentar ans Ende, NIE als vermeintlicher "Treiber"
                # fuer einen Anstieg behaupten (Feiertage/Ferien senken erfahrungsgemaess das
                # Volumen, sie erhoehen es nicht per se).
                entry['i'] = calendar_note + (' (Hinweis: Volumen heute erhöht — ungewöhnlich für diesen Kontext)' if inv_direction == 1 else '')
                top_intents.append(entry)

        anomalies.append({
            'd': d,
            'inv': inv_series[d],
            'con': dt_con[d],
            'cr': cr_series[d],
            'flags': flags,
            'top_intents': top_intents[:6],
            **({'holiday': ctx['holiday']} if ctx.get('holiday') else {}),
            **({'school_holiday': ctx['school_holiday']} if ctx.get('school_holiday') else {}),
        })

print(f'{len(anomalies)} anomalous days detected out of {len(days)} days (|z| >= {Z_THRESH}, same-weekday {WEEKDAY_WINDOW}-occurrence trailing baseline)')

WEEKDAY_NAMES_DE = ['Mo','Di','Mi','Do','Fr','Sa','So']
for row_out in daily_totals:
    row_out['wd'] = WEEKDAY_NAMES_DE[datetime.strptime(row_out['d'], '%Y-%m-%d').weekday()]
for a in anomalies:
    a['wd'] = WEEKDAY_NAMES_DE[datetime.strptime(a['d'], '%Y-%m-%d').weekday()]

DAILY_DATA = {
    'days': days,
    'daily_totals': daily_totals,
    'anomalies': anomalies,
    'window': WEEKDAY_WINDOW,
    'z_thresh': Z_THRESH,
    'baseline_mode': 'same_weekday',
}

with open(os.path.join(OUT,'DATA.json'),'w') as f:
    json.dump(DATA, f, ensure_ascii=False)
with open(os.path.join(OUT,'WOW_DATA.json'),'w') as f:
    json.dump(WOW_DATA, f, ensure_ascii=False)
with open(os.path.join(OUT,'DAILY_DATA.json'),'w') as f:
    json.dump(DAILY_DATA, f, ensure_ascii=False)
print('done')
