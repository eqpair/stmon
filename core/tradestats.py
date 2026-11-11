"""완료·보유 거래의 진입 Z·진입 Edge·청산 Z 계산 → data/trade-stats.json (Report 표시용)."""
import json, os
import numpy as np, pandas as pd
from . import data

def _at(h, x, d, win=120):
    i = h.index.searchsorted(pd.Timestamp(d), side='right') - 1     # 그날(없으면 직전 거래일)
    if i < 60:
        return None, None
    w = x.iloc[max(0, i - win):i]                                    # 당일 제외 120일
    s = w.std()
    if not s or s != s:
        return None, None
    z = (x.iloc[i] - w.mean()) / s
    return round(float(z), 3), round(float((z - 0.4) * s), 4)

def build():
    T = json.load(open(os.path.join(data.ROOT, 'data', 'pair-trades.json'), encoding='utf-8'))
    G = {}
    for t in T:
        g = G.setdefault(t['common_code'], dict(pref=t['preferred_code'], entry=t['entry_date'], exit=None, open=False))
        g['entry'] = min(g['entry'], t['entry_date'])
        if t.get('status') == 'Open':
            g['open'] = True
        if t.get('exit_date') and (not g['exit'] or t['exit_date'] > g['exit']):
            g['exit'] = t['exit_date']
    out = {}
    for c, g in G.items():
        f = os.path.join(data.HIST, f"{c}_{g['pref']}.csv")
        if not os.path.exists(f):
            continue
        h = pd.read_csv(f, index_col=0, parse_dates=True).dropna()
        x = np.log(h.C / h.P)
        ez, ee = _at(h, x, g['entry'])
        xz = _at(h, x, g['exit'])[0] if (not g['open'] and g['exit']) else None
        out[c] = dict(entry=g['entry'], entry_z=ez, entry_edge=ee, exit=None if g['open'] else g['exit'], exit_z=xz)
    p = os.path.join(data.ROOT, 'data', 'trade-stats.json')
    with open(p, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    return len(out)

if __name__ == '__main__':
    print(build())
