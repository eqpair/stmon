#!/usr/bin/env python3
"""보유 중인 페어에 이미 오간 현금(배당·롤오버 정산)을 더함. 우리 기준 부호: 받으면 +, 내면 −
사용: python3 tools/addcash.py 현대차 -1175000 1775000 "2026-04 배당"
      (종목명, 보통주 숏 다리 금액, 우선주 롱 다리 금액, 메모)"""
import json, sys
name, s, l = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); memo = sys.argv[4] if len(sys.argv) > 4 else ''
p = 'data/pair-trades.json'; t = json.load(open(p, encoding='utf-8'))
rows = [r for r in t if r.get('pair_name') == name and r.get('status') == 'Open']
if not rows: sys.exit(f'보유 중인 {name} 없음')
r = rows[0]
r['settled_s'] = round(r.get('settled_s', 0) + s); r['settled_l'] = round(r.get('settled_l', 0) + l)
r.setdefault('settled_log', []).append({'s': s, 'l': l, 'memo': memo})
json.dump(t, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"{name}: settled_s {r['settled_s']:,} / settled_l {r['settled_l']:,} (이번 {s+l:+,.0f})")
