"""Inject DATA / WOW_DATA (and DAILY_DATA if present) JSON into the dashboard HTML.

Usage: python3 inject.py <index.html> <json-dir>

Uses bracket-matching positional replacement (never str.find-based insertion, which once
corrupted the file with duplicate <!DOCTYPE>/const DATA blocks) and verifies that each
marker occurs exactly once before and after.
"""
import json, os, re, sys

html_path, json_dir = sys.argv[1], sys.argv[2]
html = open(html_path, encoding='utf-8').read()

def replace_block(html, marker, obj):
    assert len(re.findall(re.escape(marker), html)) == 1, f'{marker!r} must occur exactly once'
    start = html.index(marker) + len(marker)
    depth = 0; i = start; started = False
    while i < len(html):
        c = html[i]
        if c == '{':
            depth += 1; started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                break
        i += 1
    else:
        raise SystemExit(f'no closing brace for {marker!r}')
    return html[:start] + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + html[i + 1:]

assert len(re.findall(r'<!DOCTYPE', html)) == 1
for name in ('DATA', 'WOW_DATA', 'DAILY_DATA'):
    p = os.path.join(json_dir, name + '.json')
    if os.path.exists(p):
        html = replace_block(html, f'const {name} = ', json.load(open(p, encoding='utf-8')))
        print(f'injected {name}')
for marker in ('<!DOCTYPE', 'const DATA = ', 'const WOW_DATA = ', 'const DAILY_DATA = '):
    assert len(re.findall(re.escape(marker), html)) == 1, f'post-check failed for {marker!r}'
open(html_path, 'w', encoding='utf-8').write(html)
print('post-verify OK, size', len(html))
