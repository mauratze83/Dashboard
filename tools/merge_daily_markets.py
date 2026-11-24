"""Hängt die je Markt berechneten Tagesanomalien an DAILY_DATA an (Feld by_market).

Usage: python3 merge_daily_markets.py <DAILY_DATA.json> <ordner mit <Markt>/DAILY_DATA.json>
"""
import json, os, sys

LABEL = {'Mobilfunk': 'Mobilfunk', 'Dsl': 'DSL', 'Kabel': 'Kabel', 'Unity': 'Unity', 'Callya': 'CallYa', 'Fusionc': 'FusionC'}
target, src = sys.argv[1], sys.argv[2]
D = json.load(open(target, encoding='utf-8'))
D['by_market'] = {}
for m in LABEL:
    p = os.path.join(src, m, 'DAILY_DATA.json')
    if not os.path.exists(p):
        continue
    M = json.load(open(p, encoding='utf-8'))
    D['by_market'][m] = {'daily_totals': [{k: r[k] for k in ('d', 'inv', 'con', 'cr')} for r in M['daily_totals']],
                         'anomalies': M['anomalies']}
    print(f"{LABEL[m]}: {len(M['anomalies'])} auffällige Tage")
json.dump(D, open(target, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
