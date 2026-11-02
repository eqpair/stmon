"""
체결 장부 — data/pair-trades.json (기존 웹 화면들과 같은 형식)

체결은 직접 하고, 결과를 텔레그램 /in /out 으로 입력하면 이 장부에 기록된다.
손익은 고객(내) 관점: 숏 보통주 + 롱 우선주 + 스왑 금리(롱은 기준금리+스프레드 지급, 숏은 기준금리+스프레드 수취).
"""
from __future__ import annotations
import json, os
from dataclasses import dataclass
from datetime import date, datetime
from .data import ROOT, write_json

TRADES = os.environ.get('STMON_TRADES', os.path.join(ROOT, 'data', 'pair-trades.json'))


def load() -> list[dict]:
    try:
        return json.load(open(TRADES, encoding='utf-8'))
    except FileNotFoundError:
        return []


def save(trades: list[dict]):
    write_json(trades, TRADES)


@dataclass
class Position:
    code: str
    pref: str
    name: str
    entry_date: str
    c0: float           # 보통주 평균 진입가
    p0: float           # 우선주 평균 진입가
    cq: int
    pq: int
    bench: float        # 기준금리(%)
    sp_short: float     # 숏 스프레드(bp, 보통 음수)
    sp_long: float      # 롱 스프레드(bp)
    borrow: float       # 차입수수료(%)

    @property
    def notional(self):
        return self.c0 * self.cq + self.p0 * self.pq

    def pnl(self, c: float, p: float, on: date | None = None) -> dict:
        """평가손익(원)과 레그 기준 수익률. 금리는 실제 일수/365 (stmon 기존 계산식과 동일)."""
        on = on or date.today()
        days = max((on - date.fromisoformat(self.entry_date)).days, 0)
        eq_s = (self.c0 - c) * self.cq
        eq_l = (p - self.p0) * self.pq
        fl_s = self.c0 * self.cq * (self.bench / 100 + self.sp_short / 1e4) * days / 365     # 숏: 수취
        fl_l = -self.p0 * self.pq * (self.bench / 100 + self.sp_long / 1e4) * days / 365     # 롱: 지급
        bor = -self.c0 * self.cq * self.borrow / 100 * days / 365
        total = eq_s + eq_l + fl_s + fl_l + bor
        leg = max(self.c0 * self.cq, self.p0 * self.pq)
        return dict(days=days, equity=eq_s + eq_l, financing=fl_s + fl_l + bor, total=total,
                    ret=total / leg if leg else 0.0,
                    ret_strategy=(self.c0 - c) / self.c0 + (p - self.p0) / self.p0)   # 전략 규칙(손절 판단)용


def open_positions(trades: list[dict] | None = None) -> dict[str, Position]:
    """Open 거래를 보통주 코드별로 합침(수량가중 평균가)."""
    pos: dict[str, dict] = {}
    for t in (trades if trades is not None else load()):
        if t.get('status') != 'Open':
            continue
        a = t['common_code']
        d = pos.setdefault(a, dict(code=a, pref=t['preferred_code'], name=t.get('pair_name', a),
                                   entry_date=t['entry_date'], cv=0.0, pv=0.0, cq=0, pq=0,
                                   bench=t.get('benchmark_rate_pct', 0) or 0,
                                   sp_short=t.get('common_floating_spread_bps', -202) or 0,
                                   sp_long=t.get('preferred_floating_spread_bps', 200) or 0,
                                   borrow=t.get('common_borrow_fee_pct', 0) or 0))
        d['entry_date'] = min(d['entry_date'], t['entry_date'])
        d['cv'] += t['common_entry'] * t['common_qty']
        d['pv'] += t['preferred_entry'] * t['preferred_qty']
        d['cq'] += t['common_qty']
        d['pq'] += t['preferred_qty']
    out = {}
    for a, d in pos.items():
        if d['cq'] <= 0 or d['pq'] <= 0:
            continue
        out[a] = Position(code=a, pref=d['pref'], name=d['name'], entry_date=d['entry_date'],
                          c0=d['cv'] / d['cq'], p0=d['pv'] / d['pq'], cq=d['cq'], pq=d['pq'],
                          bench=d['bench'], sp_short=d['sp_short'], sp_long=d['sp_long'], borrow=d['borrow'])
    return out


def record_entry(code: str, pref: str, name: str, cq: int, c_px: float, pq: int, p_px: float,
                 bench: float, sp_short: float, sp_long: float, when: date | None = None) -> dict:
    trades = load()
    when = when or date.today()
    tid = f"{code}-{when:%Y%m%d}-{sum(1 for t in trades if t['common_code'] == code) + 1}"
    t = dict(trade_id=tid, pair_name=name, common_code=code, preferred_code=pref,
             entry_date=when.isoformat(), exit_date=None, common_entry=c_px, preferred_entry=p_px,
             common_qty=int(cq), preferred_qty=int(pq), common_floating_spread_bps=sp_short,
             preferred_floating_spread_bps=sp_long, benchmark_rate_pct=bench,
             common_exit=None, preferred_exit=None, common_borrow_fee_pct=0, status='Open',
             recorded_at=datetime.now().isoformat(timespec='seconds'))
    trades.insert(0, t)
    save(trades)
    return t


def record_exit(code: str, c_px: float, p_px: float, reason: str = '', when: date | None = None) -> list[dict]:
    """해당 보통주 코드의 Open 거래를 모두 청산 처리."""
    trades = load()
    when = when or date.today()
    closed = []
    for t in trades:
        if t.get('status') == 'Open' and t['common_code'] == code:
            t.update(exit_date=when.isoformat(), common_exit=c_px, preferred_exit=p_px, status='Closed',
                     exit_reason=reason.upper() or None, recorded_exit_at=datetime.now().isoformat(timespec='seconds'))
            closed.append(t)
    if closed:
        save(trades)
    return closed


def realized(trades: list[dict] | None = None) -> list[dict]:
    """청산 거래별 실현손익(고객 관점)."""
    out = []
    for t in (trades if trades is not None else load()):
        if t.get('status') != 'Closed' or not t.get('exit_date') or not t.get('common_exit'):
            continue
        p = Position(code=t['common_code'], pref=t['preferred_code'], name=t.get('pair_name', ''),
                     entry_date=t['entry_date'], c0=t['common_entry'], p0=t['preferred_entry'],
                     cq=t['common_qty'], pq=t['preferred_qty'], bench=t.get('benchmark_rate_pct', 0) or 0,
                     sp_short=t.get('common_floating_spread_bps', -202) or 0,
                     sp_long=t.get('preferred_floating_spread_bps', 200) or 0,
                     borrow=t.get('common_borrow_fee_pct', 0) or 0)
        r = p.pnl(t['common_exit'], t['preferred_exit'], date.fromisoformat(t['exit_date']))
        out.append(dict(trade_id=t.get('trade_id'), code=p.code, name=p.name, entry=p.entry_date,
                        exit=t['exit_date'], reason=t.get('exit_reason'), **r))
    return out
