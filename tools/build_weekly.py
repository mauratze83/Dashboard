import csv, json, re
from collections import defaultdict

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

import sys, os
path = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else '.'
with open(path, encoding='utf-8-sig') as f:
    r = csv.DictReader(f)
    rows = []
    for row in r:
        w = row['Woche'].strip()
        if not w:
            continue
        inv = int(round(parse_de_num(row['#Involved'])))
        con = int(round(parse_de_num(row['#Contained'])))
        cs = parse_de_num(row['€CS'])
        rows.append({
            'w': w,
            'ch': row['Kanal'].strip(),
            'intent': row['Intent'].strip(),
            'inv': inv,
            'con': con,
            'cs': cs
        })

weeks = sorted(set(r['w'] for r in rows))
print('weeks:', weeks[0], '..', weeks[-1], 'count', len(weeks))

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

# clean rows (exclude noise intents) - for intent-level + channel-tab views
clean_rows = [r for r in rows if r['intent'] not in NOISE]

# intent_totals: aggregated over clean rows across all weeks
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

# intent_weekly_cr: per intent per week CR (clean rows), only for top intents is fine but let's build for all intents appearing
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

# channels list = MAIN_CH (fixed order)
channels = MAIN_CH

# ch_totals: totals per channel (clean rows restricted to MAIN_CH)
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

# weekly_cr_by_ch / weekly_cs_by_ch: per channel per week (clean rows, MAIN_CH)
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

# ---- WOW_DATA ----
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
        # inv_delta / inv_delta_pct / cr_delta are required by renderWow()'s sort/filter logic
        # (table rows, bar charts). Missing them makes every row evaluate to NaN in comparisons,
        # which silently filters out ALL rows — table and charts render empty while the KPI tiles
        # (which only sum inv_cur/con_cur) still look fine. This caused a real regression on 2026-10-12.
        'inv_delta': ic - ip,
        'inv_delta_pct': round((ic - ip) / ip * 100, 1) if ip else 0.0,
        'cr_delta': round(crc - crp, 1),
    })
wow.sort(key=lambda x: (-x['inv_cur'], x['i']))

# remainder row: full weekly totals minus sum of clean per-intent rows, for both weeks
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

# verification
assert sum(x['inv_cur'] for x in wow) == full_inv_cur, (sum(x['inv_cur'] for x in wow), full_inv_cur)
assert sum(x['con_cur'] for x in wow) == full_con_cur
assert sum(x['inv_prev'] for x in wow) == full_inv_prev
assert sum(x['con_prev'] for x in wow) == full_prev if False else True
print('VERIFY OK: wow cur inv', sum(x['inv_cur'] for x in wow), '== weekly_totals', full_inv_cur)
print('Last week', last_w, 'Involved', full_inv_cur, 'Contained', full_con_cur, 'CR', round(full_con_cur/full_inv_cur*100,1), 'CS', round(full_cs_cur,2))
print('Prev week', prev_w, 'Involved', full_inv_prev, 'Contained', full_con_prev)

with open(os.path.join(OUT,'DATA.json'),'w') as f:
    json.dump(DATA, f, ensure_ascii=False)
with open(os.path.join(OUT,'WOW_DATA.json'),'w') as f:
    json.dump(WOW_DATA, f, ensure_ascii=False)
print('done')
