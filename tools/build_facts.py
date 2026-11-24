"""Build FACTS.json: weekly fact table (week x channel x market x intent) for the market views.

Usage: python3 build_facts.py <data/weekly.csv> <out-dir>

Compact column format (dictionary-encoded):
  {"w":[weeks], "ch":[channels], "m":[markets], "i":[intents],
   "r":[[week_idx...],[ch_idx...],[m_idx...],[i_idx...],[inv...],[con...],[cs_euro_int...]]}
All markets and channels are included (also "Kein Markt", ABC, SMS), so the page can derive
both market views and data-quality shares. Rows with Involved = 0 are dropped.
"""
import csv, json, os, sys

src, out = sys.argv[1], sys.argv[2]


def num(s):
    s = (s or '').strip().replace('%', '')
    return float(s.replace('.', '').replace(',', '.')) if s else 0.0


agg = {}
with open(src, encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f):
        k = (r['Woche'], r['Kanal'], r.get('Markt') or 'kumuliert', r['Intent'])
        a = agg.setdefault(k, [0, 0, 0.0])
        a[0] += int(r['#Involved'])
        a[1] += int(r['#Contained'])
        a[2] += num(r['€CS'])

W = sorted({k[0] for k in agg})
CH = sorted({k[1] for k in agg})
M = sorted({k[2] for k in agg})
I = sorted({k[3] for k in agg})
wi, ci, mi, ii = ({v: n for n, v in enumerate(x)} for x in (W, CH, M, I))
cols = [[] for _ in range(7)]
for k in sorted(agg):
    inv, con, cs = agg[k]
    if inv <= 0:
        continue
    for c, v in zip(cols, (wi[k[0]], ci[k[1]], mi[k[2]], ii[k[3]], inv, con, int(round(cs)))):
        c.append(v)
facts = {'w': W, 'ch': CH, 'm': M, 'i': I, 'r': cols}
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, 'FACTS.json'), 'w', encoding='utf-8') as f:
    json.dump(facts, f, ensure_ascii=False, separators=(',', ':'))
print(f'FACTS: {len(cols[0])} Zeilen, {len(W)} Wochen, Märkte: {", ".join(M)}')
