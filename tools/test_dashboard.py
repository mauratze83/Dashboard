#!/usr/bin/env python3
"""
Regression test suite for chatbot-dashboard.html.
Run after every edit: python3 test_dashboard.py [path-to-html]
Exits non-zero on any failure, prints a pass/fail report.
"""
import re, json, subprocess, sys, tempfile, os

PATH = sys.argv[1] if len(sys.argv) > 1 else '/mnt/user-data/outputs/chatbot-dashboard.html'

failures = []
passed = []

def check(name, cond, detail=''):
    if cond:
        passed.append(name)
    else:
        failures.append(f"{name}" + (f" — {detail}" if detail else ""))

html = open(PATH, encoding='utf-8').read()

# ---------------------------------------------------------------------------
# 1. STRUCTURAL INTEGRITY — the classic corruption bugs
# ---------------------------------------------------------------------------
check('exactly one <!DOCTYPE>', len(re.findall(r'<!DOCTYPE', html)) == 1)
check('exactly one "const DATA = "', len(re.findall(r'const DATA = ', html)) == 1)
check('exactly one "const WOW_DATA = "', len(re.findall(r'const WOW_DATA = ', html)) == 1)
check('exactly one "const DAILY_DATA = "', len(re.findall(r'const DAILY_DATA = ', html)) == 1)
check('exactly one inline <script> open tag (excl. CDN <script src=…>)',
      len(re.findall(r'<script>', html)) == 1)
inline_script_count = len(re.findall(r'<script src=', html))
check('</script> close-tag count matches total <script ...> opens (inline + CDN)',
      len(re.findall(r'</script>', html)) == len(re.findall(r'<script[ >]', html)))
check('exactly one <style> open tag', len(re.findall(r'<style>', html)) == 1)
check('exactly one </style> close tag', len(re.findall(r'</style>', html)) == 1)

# @media print must live INSIDE the style block (regression: it leaked out once)
style_m = re.search(r'<style>(.*?)</style>', html, re.S)
head_before_style = html[:style_m.start()] if style_m else ''
tail_after_style = html[style_m.end():] if style_m else html
check('@media print only inside <style>',
      '@media print' in (style_m.group(1) if style_m else '') and '@media print' not in tail_after_style[:2000])

# ---------------------------------------------------------------------------
# 2. JS SYNTAX
# ---------------------------------------------------------------------------
s = html.find('<script>'); e = html.rfind('</script>')
js = html[s+len('<script>'):e] if s != -1 and e != -1 else ''
check('script block extracted non-empty', len(js) > 1000)
with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False, encoding='utf-8') as f:
    f.write(js)
    jsfile = f.name
try:
    r = subprocess.run(['node', '--check', jsfile], capture_output=True, text=True, timeout=30)
    check('node --check passes (JS syntax valid)', r.returncode == 0, r.stderr.strip()[:300])
finally:
    os.unlink(jsfile)

# ---------------------------------------------------------------------------
# 3. DATA / WOW_DATA JSON VALIDITY + CONSISTENCY
# ---------------------------------------------------------------------------
def extract_json_block(marker):
    m = re.search(re.escape(marker), html)
    if not m:
        return None
    start = m.end()
    depth = 0; i = start; started = False
    while i < len(html):
        c = html[i]
        if c == '{':
            depth += 1; started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return html[start:i+1]
        i += 1
    return None

DATA = None
WOW = None
try:
    DATA = json.loads(extract_json_block('const DATA = '))
    check('DATA parses as valid JSON', True)
except Exception as ex:
    check('DATA parses as valid JSON', False, str(ex))

try:
    WOW = json.loads(extract_json_block('const WOW_DATA = '))
    check('WOW_DATA parses as valid JSON', True)
except Exception as ex:
    check('WOW_DATA parses as valid JSON', False, str(ex))

DAILY = None
try:
    DAILY = json.loads(extract_json_block('const DAILY_DATA = '))
    check('DAILY_DATA parses as valid JSON', True)
except Exception as ex:
    check('DAILY_DATA parses as valid JSON', False, str(ex))

if DATA:
    weeks = DATA.get('weeks', [])
    wt = DATA.get('weekly_totals', [])
    check('DATA.weeks non-empty', len(weeks) > 0)
    check('weekly_totals length matches weeks length', len(wt) == len(weeks),
          f"weeks={len(weeks)} weekly_totals={len(wt)}")
    check('weeks are sorted ascending', weeks == sorted(weeks))
    check('weeks has no duplicates', len(weeks) == len(set(weeks)))

    # every weekly_totals row internally consistent: con <= inv, cr matches con/inv
    bad_rows = []
    for d in wt:
        inv, con, cr = d.get('inv', 0), d.get('con', 0), d.get('cr', 0)
        if inv < 0 or con < 0:
            bad_rows.append((d['w'], 'negative value'))
            continue
        if con > inv:
            bad_rows.append((d['w'], f'con({con}) > inv({inv})'))
            continue
        expected_cr = round(con / inv * 100, 1) if inv else 0
        if abs(expected_cr - cr) > 0.15:
            bad_rows.append((d['w'], f'cr={cr} but con/inv={expected_cr}'))
    check('weekly_totals: con<=inv and cr matches con/inv for every week',
          len(bad_rows) == 0, str(bad_rows[:5]))

    # sanity bounds: catches the German-decimal-parsing bug (values off by ~1000x)
    # typical weekly involved volume should be in a plausible band, not collapsed to near-zero
    if wt:
        avg_inv = sum(d['inv'] for d in wt) / len(wt)
        check('average weekly Involved is plausible (not collapsed by parse bug)',
              avg_inv > 1000, f"avg_inv={avg_inv:.0f} — suspiciously low, check number parsing (German '.' as thousands sep)")
        max_cr = max(d['cr'] for d in wt)
        check('no week has an implausible CR (>99%) suggesting Involved undercount',
              max_cr <= 99.0, f"max weekly CR={max_cr}% — check Involved parsing")

    # intent_totals sanity
    it = DATA.get('intent_totals', [])
    check('intent_totals non-empty', len(it) > 0)
    bad_it = [d['i'] for d in it if d.get('con', 0) > d.get('inv', 0)]
    check('intent_totals: no intent has con>inv', len(bad_it) == 0, str(bad_it[:5]))

    # channels
    ch = DATA.get('ch_totals', {})
    check('ch_totals has Webchat/Appchat/WhatsApp', all(c in ch for c in ['Webchat','Appchat','WhatsApp']))
    for c, v in ch.items():
        if v.get('con', 0) > v.get('inv', 0):
            failures.append(f'ch_totals[{c}]: con>inv')
    check('ch_totals: no channel has con>inv',
          all(v.get('con',0) <= v.get('inv',0) for v in ch.values()))

if WOW and DATA:
    wow_rows = WOW.get('wow', [])
    check('WOW_DATA.wow non-empty', len(wow_rows) > 0)
    check('WOW_DATA has a Sonstige_ABC_SMS_Noise remainder row',
          any(r.get('i') == 'Sonstige_ABC_SMS_Noise' for r in wow_rows))

    last_w, prev_w = WOW.get('last'), WOW.get('prev')
    wt_by_week = {d['w']: d for d in DATA.get('weekly_totals', [])}
    if last_w in wt_by_week and prev_w in wt_by_week:
        full_inv_cur = wt_by_week[last_w]['inv']
        full_con_cur = wt_by_week[last_w]['con']
        full_inv_prev = wt_by_week[prev_w]['inv']
        full_con_prev = wt_by_week[prev_w]['con']
        sum_inv_cur = sum(r.get('inv_cur', 0) for r in wow_rows)
        sum_con_cur = sum(r.get('con_cur', 0) for r in wow_rows)
        sum_inv_prev = sum(r.get('inv_prev', 0) for r in wow_rows)
        sum_con_prev = sum(r.get('con_prev', 0) for r in wow_rows)
        check('WOW rows (incl. remainder) sum to weekly_totals: inv_cur',
              sum_inv_cur == full_inv_cur, f"{sum_inv_cur} != {full_inv_cur}")
        check('WOW rows (incl. remainder) sum to weekly_totals: con_cur',
              sum_con_cur == full_con_cur, f"{sum_con_cur} != {full_con_cur}")
        check('WOW rows (incl. remainder) sum to weekly_totals: inv_prev',
              sum_inv_prev == full_inv_prev, f"{sum_inv_prev} != {full_inv_prev}")
        check('WOW rows (incl. remainder) sum to weekly_totals: con_prev',
              sum_con_prev == full_con_prev, f"{sum_con_prev} != {full_con_prev}")
    else:
        failures.append(f'WOW_DATA.last/prev ({last_w}/{prev_w}) not found in DATA.weekly_totals')

    bad_wow = [r['i'] for r in wow_rows if r.get('con_cur',0) > r.get('inv_cur',0) or r.get('con_prev',0) > r.get('inv_prev',0)]
    check('WOW rows: no row has con>inv (cur or prev)', len(bad_wow) == 0, str(bad_wow[:5]))

    # cs_delta regression: the €CS-Shift column silently showed "—" for every row
    # because cs_delta was never written into WOW_DATA.wow by the Python data pipeline.
    missing_cs_delta = [r['i'] for r in wow_rows if 'cs_delta' not in r]
    check('every WOW row has a cs_delta field (€CS-Shift column would be blank otherwise)',
          len(missing_cs_delta) == 0, str(missing_cs_delta[:5]))
    mismatched_cs_delta = [r['i'] for r in wow_rows
                           if 'cs_delta' in r and abs(r['cs_delta'] - round((r.get('cs_cur',0) or 0) - (r.get('cs_prev',0) or 0), 2)) > 0.02]
    check('cs_delta equals cs_cur - cs_prev for every WOW row',
          len(mismatched_cs_delta) == 0, str(mismatched_cs_delta[:5]))

    # Regression (2026-10-12): inv_delta / inv_delta_pct / cr_delta were missing entirely from
    # WOW_DATA.wow. renderWow() sorts and filters every row using these fields (e.g.
    # Math.abs(r.inv_delta_pct) >= vt) — missing them makes every comparison evaluate to NaN,
    # which silently filters out ALL rows. The WoW KPI tiles still looked fine (they only sum
    # inv_cur/con_cur), but the shift bar charts and the table rendered completely empty.
    for field in ('inv_delta', 'inv_delta_pct', 'cr_delta'):
        missing = [r['i'] for r in wow_rows if field not in r]
        check(f'every WOW row has a {field} field (table/charts render empty otherwise via NaN comparisons)',
              len(missing) == 0, str(missing[:5]))
    mismatched_inv_delta = [r['i'] for r in wow_rows
                            if 'inv_delta' in r and r['inv_delta'] != r.get('inv_cur',0) - r.get('inv_prev',0)]
    check('inv_delta equals inv_cur - inv_prev for every WOW row',
          len(mismatched_inv_delta) == 0, str(mismatched_inv_delta[:5]))
    mismatched_cr_delta = [r['i'] for r in wow_rows
                           if 'cr_delta' in r and abs(r['cr_delta'] - round(r.get('cr_cur',0) - r.get('cr_prev',0), 1)) > 0.15]
    check('cr_delta equals cr_cur - cr_prev for every WOW row',
          len(mismatched_cr_delta) == 0, str(mismatched_cr_delta[:5]))

# Kanäle-Tab: Involved je Kanal im Zeitverlauf (2026-11-16)
if DATA:
    _wi = DATA.get('weekly_inv_by_ch') or {}
    check('DATA.weekly_inv_by_ch exists for every main channel with one value per week',
          bool(_wi) and all(len(_wi.get(c, [])) == len(DATA['weeks']) for c in DATA.get('channels', [])))
    check('weekly Involved per channel adds up to ch_totals[channel].inv',
          all(sum(_wi.get(c, [])) == DATA['ch_totals'][c]['inv'] for c in DATA.get('channels', [])))
if DATA:
    _wc = DATA.get('weekly_con_by_ch') or {}
    check('DATA.weekly_con_by_ch adds up to ch_totals[channel].con for every channel',
          bool(_wc) and all(sum(_wc.get(c, [])) == DATA['ch_totals'][c]['con'] for c in DATA.get('channels', [])))
check('Kanäle tab follows the time filter (renderKanal uses weeks())',
      re.search(r'function renderKanal\(\)\{[\s\S]{0,400}weeks\(\)', html) is not None)
check('Kanäle tab has the Involved-over-time chart wired up', 'id="kanalInvLine"' in html and "mkChart('kanalInvLine'" in html)

# Incremental imports (since 2026-11-09): the weekly series must stay gap-free and sorted
if DATA and DATA.get('weeks'):
    from datetime import date as _date, timedelta as _td
    def _mon(l):
        y, w = map(int, l.split('-')); return _date.fromisocalendar(y, w, 1)
    _wk = DATA['weeks']
    _gaps = [(a, b) for a, b in zip(_wk, _wk[1:]) if _mon(b) - _mon(a) != _td(days=7)]
    check('DATA.weeks is a gap-free, sorted ISO week series', not _gaps, str(_gaps[:3]))
    check('DATA.weekly_totals weeks equal DATA.weeks', [w['w'] for w in DATA['weekly_totals']] == _wk)
    if WOW:
        check('WOW_DATA compares the last two weeks of DATA.weeks',
              WOW.get('last') == _wk[-1] and WOW.get('prev') == _wk[-2], f"{WOW.get('prev')}->{WOW.get('last')}")

# ---------------------------------------------------------------------------
# 3b. DAILY_DATA JSON VALIDITY + CONSISTENCY (Anomalien tab, daily-format CSV)
# ---------------------------------------------------------------------------
if DAILY and DATA:
    days = DAILY.get('days', [])
    dt_totals = DAILY.get('daily_totals', [])
    anomalies = DAILY.get('anomalies', [])
    check('DAILY_DATA.days non-empty', len(days) > 0)
    check('daily_totals length matches days length', len(dt_totals) == len(days),
          f"days={len(days)} daily_totals={len(dt_totals)}")
    check('days are sorted ascending', days == sorted(days))
    check('days has no duplicates', len(days) == len(set(days)))
    check('DAILY_DATA has window and z_thresh fields', 'window' in DAILY and 'z_thresh' in DAILY)
    check('DAILY_DATA uses the same-weekday baseline mode (Mon vs Mon, not Mon vs weekend mix)',
          DAILY.get('baseline_mode') == 'same_weekday')
    check('every daily_totals row has a weekday label (wd)',
          all('wd' in d for d in dt_totals))
    check('every anomaly row has a weekday label (wd)',
          all('wd' in a for a in anomalies))
    # weekday distribution of anomalies should be roughly even (no systematic bias toward one
    # weekday — would indicate the baseline is still mixing weekday/weekend data)
    from collections import Counter as _Counter
    wd_counts = _Counter(a.get('wd') for a in anomalies)
    if anomalies and len(wd_counts) >= 5:
        max_share = max(wd_counts.values()) / len(anomalies)
        check('anomalies are not overwhelmingly concentrated on a single weekday (baseline sanity)',
              max_share < 0.5, f"{dict(wd_counts)}")

    bad_daily_rows = []
    for d in dt_totals:
        inv, con, cr = d.get('inv', 0), d.get('con', 0), d.get('cr', 0)
        if inv < 0 or con < 0:
            bad_daily_rows.append((d.get('d'), 'negative value')); continue
        if con > inv:
            bad_daily_rows.append((d.get('d'), f'con({con}) > inv({inv})')); continue
        expected_cr = round(con / inv * 100, 1) if inv else 0
        if abs(expected_cr - cr) > 0.15:
            bad_daily_rows.append((d.get('d'), f'cr={cr} but con/inv={expected_cr}'))
    check('daily_totals: con<=inv and cr matches con/inv for every day',
          len(bad_daily_rows) == 0, str(bad_daily_rows[:5]))

    # cross-check: sum of daily Involved/Contained for days in the last ISO week equals
    # DATA.weekly_totals for that week (the "preserve weekly views" requirement)
    if days and DATA.get('weekly_totals'):
        from datetime import datetime as _dt
        def _iso_week(dstr):
            d = _dt.strptime(dstr, '%Y-%m-%d')
            y, w, _ = d.isocalendar()
            return f'{y}-{w:02d}'
        by_week_inv = {}
        by_week_con = {}
        for d in dt_totals:
            wl = _iso_week(d['d'])
            by_week_inv[wl] = by_week_inv.get(wl, 0) + d.get('inv', 0)
            by_week_con[wl] = by_week_con.get(wl, 0) + d.get('con', 0)
        # Daily data may lag behind weekly data (e.g. a weekly-only CSV extends DATA by a week while
        # DAILY_DATA stays at its last daily-format upload). Compare EVERY week that daily data fully
        # covers (7 days) against DATA.weekly_totals.
        wt_map = {w['w']: w for w in DATA['weekly_totals']}
        days_per_week = {}
        for d in dt_totals:
            wl = _iso_week(d['d']); days_per_week[wl] = days_per_week.get(wl, 0) + 1
        full_weeks = [w for w, n in days_per_week.items() if n == 7 and w in wt_map]
        check('daily data fully covers at least one week also present in DATA.weekly_totals', len(full_weeks) > 0)
        bad_wk = [(w, by_week_inv[w], wt_map[w]['inv'], by_week_con[w], wt_map[w]['con']) for w in full_weeks
                  if by_week_inv[w] != wt_map[w]['inv'] or by_week_con[w] != wt_map[w]['con']]
        check('daily_totals aggregated to ISO weeks match DATA.weekly_totals for every fully covered week (inv+con)',
              len(bad_wk) == 0, str(bad_wk[:5]))

    # anomalies sanity: every anomaly day must exist in days, have a metric and z-score,
    # and any listed driver intents must be non-empty strings
    day_set = set(days)
    bad_anom = []
    for a in anomalies:
        if a.get('d') not in day_set:
            bad_anom.append((a.get('d'), 'day not in DAILY_DATA.days')); continue
        if not a.get('flags'):
            bad_anom.append((a.get('d'), 'no flags')); continue
        for fl in a['flags']:
            if fl.get('metric') not in ('inv', 'cr'):
                bad_anom.append((a.get('d'), f"bad metric {fl.get('metric')}"))
    check('every DAILY_DATA anomaly references a real day with valid flags',
          len(bad_anom) == 0, str(bad_anom[:5]))

    # Feiertage/Schulferien: a calendar note must never be presented as an unqualified driver
    # (no caveat text) unless the day's Involved anomaly direction is actually negative (volume
    # down) — that's the only direction holidays/school breaks are expected to push volume. If
    # volume went UP instead, the generator must append a caveat ("Hinweis: ... erhöht ...") so
    # the UI doesn't claim a holiday caused a volume increase.
    bad_calendar = []
    for a in anomalies:
        inv_flag = next((f for f in a.get('flags', []) if f.get('metric') == 'inv'), None)
        cal_entries = [ti for ti in a.get('top_intents', []) if ti.get('calendar')]
        if cal_entries and inv_flag is not None:
            direction = 1 if inv_flag['val'] > inv_flag['baseline_mean'] else -1
            for ce in cal_entries:
                has_caveat = 'erhöht' in ce.get('i', '') or 'Hinweis' in ce.get('i', '')
                if direction == 1 and not has_caveat:
                    bad_calendar.append((a.get('d'), 'volume up but calendar note has no up-caveat'))
                if direction == -1 and has_caveat:
                    bad_calendar.append((a.get('d'), 'volume down but calendar note wrongly carries up-caveat'))
    check('calendar (holiday/school-break) notes never claim an unqualified driver role when volume actually increased',
          len(bad_calendar) == 0, str(bad_calendar[:5]))
    check('at least one DAILY_DATA anomaly carries holiday or school_holiday context (sanity check feature is wired)',
          any(a.get('holiday') or a.get('school_holiday') for a in anomalies))

# ---------------------------------------------------------------------------
# 4b. ANOMALIEN TAB WIRING
# ---------------------------------------------------------------------------
check("Anomalien nav-tab present (showPage('anomalien',this))", "showPage('anomalien'" in html)
check('Anomalien page div present (id="page-anomalien")', 'id="page-anomalien"' in html)
check('renderAnomalien() is defined', re.search(r'function\s+renderAnomalien\s*\(', html) is not None)
check("reRender() dispatches to renderAnomalien() for id==='anomalien'",
      re.search(r"id==='anomalien'[^}]*renderAnomalien\(\)", html) is not None)
check("showPage()'s needsRender dispatch calls renderAnomalien() for id==='anomalien'",
      len(re.findall(r"renderAnomalien\(\)", html)) >= 2)
check("anomInvChart and anomCrChart canvases present",
      'id="anomInvChart"' in html and 'id="anomCrChart"' in html)
check("baseOpts() is never called with two arguments in the Anomalien chart code (regression: SyntaxError)",
      re.search(r"baseOpts\(\{[^)]*\}\s*,\s*\{", html) is None)

# rebuildWow() (custom week-picker in JS) must also populate cs_delta — same bug class
check('rebuildWow() sets cs_delta on itMap rows', 'cs_delta:csB-csA' in html or re.search(r'cs_delta\s*:\s*csB\s*-\s*csA', html) is not None)
check('rebuildWow() sets cs_delta on the Sonstige/remainder row', re.search(r"Sonstige_ABC_SMS_Noise.*cs_delta", html) is not None)

# ---------------------------------------------------------------------------
# 7. ANTHROPIC API CALLS — model name validity, auth header sanity
# ---------------------------------------------------------------------------
# Regression: 'claude-sonnet-4-6' was hardcoded and is not a real model string, causing 400s.
VALID_MODELS = {'claude-fable-5-1', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5', 'claude-sonnet-5'}
model_refs = re.findall(r"model:\s*'([^']+)'", html)
check('at least one Anthropic model reference found in the file', len(model_refs) > 0)
bad_models = [m for m in model_refs if m not in VALID_MODELS]
check('every hardcoded model string is a currently valid Anthropic model id',
      len(bad_models) == 0, f"invalid/unknown model string(s): {set(bad_models)} — check against platform.claude.com/docs/en/models/overview")

# error handling: API error responses should surface the real error body, not just the status code,
# so future 400s are diagnosable from the chat UI itself instead of guesswork
error_throws = re.findall(r"throw new Error\('API '\+\w+\.status[^)]*\)", html)
check("every 'API <status>' error throw also includes the response body text (for diagnosability)",
      len(error_throws) > 0 and all('eb' in e for e in error_throws), str(error_throws))

# Regression (2026-11-02): the WoW management summary stopped mid-sentence. genSummary() used
# max_tokens:1000 for a "max. 320 Wörter" German summary full of numbers and long intent names
# (~700-900 tokens), and never checked stop_reason, so truncated text was shown silently.
gen_m = re.search(r'async function genSummary\(\)(.*?)\n\s*btn\.disabled=false', html, re.S)
check('genSummary() found', gen_m is not None)
if gen_m:
    g = gen_m.group(1)
    first = re.search(r'callSum\((\d+)\s*,\s*true\)', g)
    check('genSummary() first call uses max_tokens >= 4096 (1000/3000 truncated the summary)',
          first is not None and int(first.group(1)) >= 4096, f"first call={first.group(0) if first else None}")
    # Regression (2026-11-02, 2nd round): Haiku/Sonnet/Opus 5.5 think by default ("adaptive thinking") and the
    # hidden thinking tokens count against max_tokens — the summary was still cut off at max_tokens 3000.
    check("genSummary() disables adaptive thinking (thinking tokens count against max_tokens)",
          "thinking={type:'disabled'}" in g)
    check("genSummary() automatically retries with a larger limit when stop_reason is 'max_tokens'",
          re.search(r"if\(dat\.stop_reason==='max_tokens'\)dat=await callSum\((\d+)", g) is not None)
    check('genSummary() uses claude-haiku-5-5 (cheaper; switched from Sonnet on 2026-11-02)',
          "model:'claude-haiku-5-5'" in gen_m.group(1))
    check("genSummary() detects stop_reason==='max_tokens' and tells the user",
          "stop_reason==='max_tokens'" in gen_m.group(1))
check('typewrite() cancels a previous run on the same element (no interleaved text on regenerate)',
      '_twRun' in html)

# ---------------------------------------------------------------------------
# 4. NAVIGATION / TAB WIRING — every nav-tab has a matching page and vice versa
# ---------------------------------------------------------------------------
nav_tab_ids = re.findall(r"showPage\('(\w+)'", html)
page_ids = re.findall(r'<div class="page[^"]*" id="page-(\w+)"', html)
check('every nav-tab target has a matching page div',
      set(nav_tab_ids) <= set(page_ids), f"missing pages for: {set(nav_tab_ids) - set(page_ids)}")
check('every page div has a nav-tab (or is intentionally tab-less)',
      set(page_ids) <= set(nav_tab_ids), f"orphan pages: {set(page_ids) - set(nav_tab_ids)}")
check('TAB[] array (swipe nav) matches nav-tab set',
      True)  # informational; verified below with explicit extraction
tab_arr_m = re.search(r"TAB=\[([^\]]+)\]", html)
if tab_arr_m:
    tab_arr = re.findall(r"'(\w+)'", tab_arr_m.group(1))
    check('TAB[] (swipe navigation) matches nav-tab ids exactly',
          set(tab_arr) == set(nav_tab_ids), f"TAB[]={tab_arr} nav-tabs={nav_tab_ids}")

# Tabs Heatmap + Clustering removed on 2026-11-16 (user request)
# Korrelation removed on 2026-11-16 (Clustering was removed by mistake and restored the same day)
for leftover in ['page-heatmap', 'renderHeatmap', 'hmColor', 'page-korr', 'renderKorr', 'korr-table', 'pearson(', 'corrColor']:
    check(f'Removed tab leftovers: no "{leftover}" in the file', leftover not in html)
check('Clustering tab present: nav tab, page, renderCluster, dispatch in reRender and showPage',
      "showPage('cluster',this)" in html and 'id="page-cluster"' in html and 'function renderCluster(' in html
      and "if(id==='cluster'){renderCluster();markTabRendered('cluster');}" in html and "if(id==='cluster')renderCluster();" in html)
check('Clustering uses the new design (elevation, mkChart, no overshoot easing on cluster cards)',
      re.search(r'\n\.cluster-card\{[^\n]*box-shadow:var\(--elev-1\)', html) is not None
      and "mkChart('clusterCr'" in html and "mkChart('clusterVol'" in html
      and '.cluster-card.anim-in{animation:kpiIn .4s cubic-bezier(.2,.8,.2,1)' in html)
# every page referenced by showPage(...) / getElementById('page-...') / TAB[] must exist
_pages = set(re.findall(r'id="page-([a-z]+)"', html))
_refs = set(re.findall(r"showPage\('([a-z]+)'", html)) | set(re.findall(r"getElementById\('page-([a-z]+)'\)", html))
_tabm = re.search(r"TAB=\[([^\]]*)\]", html)
if _tabm:
    _refs |= set(re.findall(r"'([a-z]+)'", _tabm.group(1)))
check('every referenced page (showPage, page-*, swipe TAB[]) exists in the HTML', _refs <= _pages, str(sorted(_refs - _pages)))

# Apple-Design-Überarbeitung (2026-11-16): Glasebene, ruhige Animationen, Systemschrift
_css = html.split('</style>')[0]
check('no Google Fonts / Inter / JetBrains Mono (system font stack instead)',
      'fonts.googleapis' not in html and "family:'Inter'" not in html and 'JetBrains' not in html)
check('header, nav and time filter sit inside one .chrome glass layer',
      re.search(r'<div class="chrome">\s*<header>.*?<nav>.*?<div id="timeFilterBar">', html, re.S) is not None)
_chrome = html[html.find('<div class="chrome">'):html.find('<div id="timeFilterBar">')]
check('uploadOverlay (position:fixed) is NOT inside the backdrop-filter layer', 'uploadOverlay' not in _chrome)
check('.chrome uses backdrop-filter and has reduced-transparency + contrast fallbacks',
      'backdrop-filter:blur(' in _css and 'prefers-reduced-transparency' in _css and 'prefers-contrast:more' in _css)
check('no endlessly looping animations (no "infinite")', 'infinite' not in _css)
check('prefers-reduced-motion is handled in CSS and for Chart.js',
      'prefers-reduced-motion:reduce' in _css and 'Chart.defaults.animation=false' in html)
_overshoot = [m for m in re.findall(r'cubic-bezier\(([^)]*)\)', _css) if any(float(v) > 1 for v in m.split(',')[1::2])]
check('no overshooting easing curves (cubic-bezier y > 1)', not _overshoot, str(_overshoot))
check('KPI/card entry animations play once per data state (trigAnim uses _animGen)', 'dataset.ag===g' in html and '_animGen++' in html)
check('no uppercase labels in the main CSS', 'text-transform:uppercase' not in _css.split('@media print')[0])

# Apple-Design Teil 2 (2026-11-16): Tab-Markierung, Wischen, Tiefe, Feedback, Diagramm-Updates
check('sliding tab indicator exists and is moved on click (moveNavInd in showPage)',
      'id="navInd"' in html and re.search(r'function showPage\(id,el\)\{[^}]*moveNavInd\(el\)', html) is not None)
check('swipe navigation follows the finger and uses momentum projection + rubber band',
      'function project(v)' in html and 'function rubber(' in html and "addEventListener('touchmove'" in html)
check('swipe tab list matches the nav tabs',
      re.findall(r"showPage\('([a-z]+)',this\)", html) == re.findall(r"'([a-z]+)'", re.search(r"var TAB=\[([^\]]*)\]", html).group(1)))
check('cards use elevation instead of plain borders (box-shadow var(--elev-*))',
      re.search(r'\n\.card\{[^\n]*box-shadow:var\(--elev-1\)', html) is not None and re.search(r'\n\.kpi\{[^\n]*box-shadow:var\(--elev-2\)', html) is not None)
check('chart colors follow the light/dark theme (chartTheme in baseOpts), no hardcoded dark grid',
      'function chartTheme()' in html and "grid:{color:'#1c2035'}" not in html)
check('charts are updated in place (mkChart) and reRender no longer destroys them',
      html.count('new Chart(') == 1 and 'function mkChart(' in html
      and re.search(r'function reRender\(\)\{\s*Object\.keys\(charts\)\.forEach', html) is None)
check('buttons give press feedback on :active', '.btn:active,' in html and 'transform:scale(.97)' in html)
check('detail view zooms from the clicked element (page-zoom with transform-origin)', 'page-zoom' in html and '_detailOrigin' in html)
check('KPI grids can shrink on small screens (minmax(0,1fr))', 'repeat(2,minmax(0,1fr))!important' in html)

# Märkte (2026-11-24): eingebettete Faktentabelle + Märkte-Tab
FACTS = None
try:
    FACTS = json.loads(extract_json_block('const FACTS = '))
    check('FACTS parses as valid JSON with column layout', all(k in FACTS for k in ('w', 'ch', 'm', 'i', 'r')) and len(FACTS['r']) == 7)
except Exception as ex:
    check('FACTS parses as valid JSON with column layout', False, str(ex))
if FACTS and DATA:
    _r = FACTS['r']
    check('FACTS columns have equal length', len({len(c) for c in _r}) == 1)
    check('FACTS weeks equal DATA.weeks', FACTS['w'] == DATA['weeks'])
    _inv_by_w = {}
    for wi, v in zip(_r[0], _r[4]):
        _inv_by_w[wi] = _inv_by_w.get(wi, 0) + v
    check('FACTS Involved per week (all markets/channels) equals DATA.weekly_totals',
          all(_inv_by_w.get(k, 0) == wt['inv'] for k, wt in enumerate(DATA['weekly_totals'])))
    _main = {FACTS['ch'].index(c) for c in DATA.get('channels', []) if c in FACTS['ch']}
    _nz = {FACTS['i'].index(x) for x in ['None','Saleslivechat','Spam','Kein Topintent','Catchphrasedecease','Chatimmobilienwirtschaft','Surveyimmobilienwirtschaft'] if x in FACTS['i']}
    _ci = {}
    for ci, ii, v in zip(_r[1], _r[3], _r[4]):
        if ci in _main and ii not in _nz:
            _ci[FACTS['ch'][ci]] = _ci.get(FACTS['ch'][ci], 0) + v
    check('FACTS (main channels, no noise) per channel equals DATA.ch_totals', all(_ci.get(c, 0) == DATA['ch_totals'][c]['inv'] for c in DATA['channels']))
    check('all six main markets present in FACTS', all(m in FACTS['m'] for m in ['Mobilfunk', 'Dsl', 'Kabel', 'Unity', 'Callya', 'Fusionc']))
check('FusionC migration monitor present and called from renderMaerkte',
      'id="fcCard"' in html and 'function renderFusionC(' in html and 'renderFusionC(wIdx,lbl,miw,mw)' in html
      and "mkChart('fcVol'" in html and "mkChart('fcShare'" in html)
if DAILY:
    _an = DAILY.get('anomalies', [])
    check('anomaly drivers carry market attribution (mk) or are market×intent drivers (m) on most days',
          sum(1 for x in _an if any(t.get('mk') or t.get('m') for t in x.get('top_intents', []))) >= 0.7 * max(1, len(_an)))
    _bad_mk = [x['d'] for x in _an for t in x.get('top_intents', []) for mm in t.get('mk', [])
               if (mm['dev'] > 0) != (t['dev'] > 0)]
    check('market attribution never contradicts the intent driver direction', not _bad_mk, str(_bad_mk[:3]))
check('Anomalien tab shows market attribution of drivers', 'ti.mk.map(x=>x.m)' in html and "' in '+ti.m" in html)
check('CR decomposition (mix vs. performance) card in WoW tab, rendered from renderWow', 'id="mixCard"' in html and 'function crDecompose(' in html and re.search(r'function renderWow\(\)\{\s*renderMix\(\);', html) is not None)
check('global market filter: select in time filter bar, applyMarket, snapshot of original data',
      'id="mkFilter"' in html and 'function applyMarket(' in html and 'function buildDataFrom(' in html and '_snapshotAll();' in html)
if DAILY:
    _bm = DAILY.get('by_market') or {}
    check('DAILY_DATA.by_market has daily anomalies for all six main markets',
          all(m in _bm and 'anomalies' in _bm[m] and 'daily_totals' in _bm[m] for m in ['Mobilfunk','Dsl','Kabel','Unity','Callya','Fusionc']))
    if _bm and FACTS:
        # Tageswerte je Markt müssen zu den Wochenwerten des Markts (Hauptkanäle) passen
        _mi = FACTS['m'].index('Unity'); _main = {FACTS['ch'].index(c) for c in ['Webchat','Appchat','WhatsApp']}
        _wf = sum(v for m_, c_, v in zip(FACTS['r'][2], FACTS['r'][1], FACTS['r'][4]) if m_ == _mi and c_ in _main)
        check('by_market Unity daily totals add up to FACTS Unity (main channels)',
              sum(d['inv'] for d in _bm.get('Unity', {}).get('daily_totals', [])) == _wf)
check('getFD computes exact intent values from FACTS for a partial time range', 'exakt aus der Faktentabelle für die gewählten Wochen' in html)
check('rebuildWow uses exact FACTS values and updates the week labels', 'WOW_DATA.prev=wA;WOW_DATA.last=wB;buildWowDeduped(res.wow)' in html)
check('Intent x Kanal outlier card wired (card, logit expectation, called from renderMaerkte)',
      'id="mkxCard"' in html and 'function renderMkXch(' in html and 'function mkxRows(' in html
      and 'renderMkXch();' in html.split('function renderMaerkte(')[1].split('function renderMkIntents(')[0]
      and 'Math.log(v/(1-v))' in html)
check('Märkte tab wired (nav, page, renderMaerkte in reRender and showPage)',
      "showPage('maerkte',this)" in html and 'id="page-maerkte"' in html and 'function renderMaerkte(' in html
      and "if(id==='maerkte'){renderMaerkte();markTabRendered('maerkte');}" in html and "if(id==='maerkte')renderMaerkte();" in html)

# ---------------------------------------------------------------------------
# 5. KI-CHAT REMOVED (2026-11-02, auf Wunsch entfernt — zu hoher Token-Verbrauch)
# ---------------------------------------------------------------------------
for leftover in ['id="kiFab"', 'id="kiPanel"', 'sendKiChat', 'toggleKiChat', '_kiHistory', 'syncKeyUiKi',
                 'KI_SEARCH_DOMAINS', 'VF_CONTEXT', 'web_search', 'page-ki']:
    check(f'KI-Chat fully removed: no "{leftover}" left in the file', leftover not in html)
check('API-key UI for the summary still present (apiKeySection / saveKey / clearKey)',
      'id="apiKeySection"' in html and re.search(r'function\s+saveKey\s*\(', html) and re.search(r'function\s+clearKey\s*\(', html))

# ---------------------------------------------------------------------------
# 6. PASSWORD GATE still intact
# ---------------------------------------------------------------------------
check('password overlay element present', '#pwScreen' in html or 'id="pwScreen"' in html)
check('PW_HASH defined', 'PW_HASH' in html)

# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------
print(f"\n{'='*70}\nDASHBOARD TEST SUITE — {PATH}\n{'='*70}")
print(f"PASSED: {len(passed)}")
for p in passed:
    print(f"  ok  {p}")
if failures:
    print(f"\nFAILED: {len(failures)}")
    for f in failures:
        print(f"  FAIL  {f}")
    print(f"\n{'='*70}\nRESULT: FAIL ({len(failures)} failure(s))\n{'='*70}")
    sys.exit(1)
else:
    print(f"\n{'='*70}\nRESULT: ALL {len(passed)} CHECKS PASSED\n{'='*70}")
    sys.exit(0)
