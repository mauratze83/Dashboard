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
error_throws = re.findall(r"throw new Error\('API '\+resp\.status[^)]*\)", html)
check("every 'API <status>' error throw also includes the response body text (for diagnosability)",
      len(error_throws) > 0 and all('eb' in e for e in error_throws), str(error_throws))

# Regression (2026-11-02): the WoW management summary stopped mid-sentence. genSummary() used
# max_tokens:1000 for a "max. 320 Wörter" German summary full of numbers and long intent names
# (~700-900 tokens), and never checked stop_reason, so truncated text was shown silently.
gen_m = re.search(r'async function genSummary\(\)(.*?)\n\s*btn\.disabled=false', html, re.S)
check('genSummary() found', gen_m is not None)
if gen_m:
    mt = re.search(r'max_tokens\s*:\s*(\d+)', gen_m.group(1))
    check('genSummary() max_tokens >= 2000 (1000 truncated the summary mid-sentence)',
          mt is not None and int(mt.group(1)) >= 2000, f"max_tokens={mt.group(1) if mt else None}")
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
