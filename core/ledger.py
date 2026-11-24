"""
체결 장부 — data/pair-trades.json (기존 웹 화면들과 같은 형식)

체결은 직접 하고, 결과를 텔레그램 /in /out 으로 입력하면 이 장부에 기록된다.
손익은 고객(내) 관점: 숏 보통주 + 롱 우선주 + 스왑 금리(롱은 기준금리+스프레드 지급, 숏은 기준금리+스프레드 수취).
"""
from __future__ import annotations
import json, os, math
from dataclasses import dataclass, field
from datetime import date, datetime
from .data import ROOT, write_json

TRADES = os.environ.get('STMON_TRADES', os.path.join(ROOT, 'data', 'pair-trades.json'))
SETTLE = os.path.join(ROOT, 'data', 'settlements.json')
EXIT_C, EXIT_P = 0.001, 0.003     # 청산 비용: 보통주 숏 청산(매수) 수수료 10bp, 우선주 롱 청산(매도) 수수료 10bp + 거래세 20bp


def _jround(x: float) -> float:
    return math.floor(x + 0.5)    # JS Math.round 와 같게 (Report와 원 단위까지 일치)


def row_pnl(t: dict, c: float, p: float, on: date) -> dict:
    """거래 한 줄의 손익(고객 기준 +이익). pair-report.html / exit.html 과 같은 계산식:
    진입가 = 텀싯 Net, 청산가 = 체결가 × (1+10bp / 1−30bp), 롤오버된 거래는 현재 기간 기준가(current.s0)·CD로 평가,
    이미 오간 현금(롤오버 정산·배당 settled_s/l)을 더함."""
    cur = t.get('current') or None
    q, Q = t['common_qty'], t['preferred_qty']
    c0 = cur['common_s0'] if cur else t['common_entry']
    p0 = cur['preferred_s0'] if cur else t['preferred_entry']
    days = max(1, (on - date.fromisoformat(t['entry_date'])).days)
    fd = max(1, (on - date.fromisoformat(cur['start'])).days) if cur else days
    rate = cur['cd'] if cur and cur.get('cd') is not None else (t.get('benchmark_rate_pct') or 0)
    sS = (t['common_floating_spread_bps'] if t.get('common_floating_spread_bps') is not None else -202) / 1e4
    sL = (t['preferred_floating_spread_bps'] if t.get('preferred_floating_spread_bps') is not None else 200) / 1e4
    eq_s = (c0 - c * (1 + EXIT_C)) * q
    eq_l = (p * (1 - EXIT_P) - p0) * Q
    fl_s = _jround(c0 * q * (rate / 100 + sS) * fd / 365)
    fl_l = -_jround(p0 * Q * (rate / 100 + sL) * fd / 365)
    bor = -c0 * q * ((t.get('common_borrow_fee_pct') or 0) / 100) * fd / 365
    ss, sl = t.get('settled_s') or 0, t.get('settled_l') or 0
    s_leg, l_leg = eq_s + fl_s + bor + ss, eq_l + fl_l + sl
    return dict(days=days, equity=eq_s + eq_l, financing=fl_s + fl_l + bor, settled=ss + sl,
                s=s_leg, l=l_leg, total=s_leg + l_leg)


def settlements() -> dict:
    try:
        return json.load(open(SETTLE, encoding='utf-8'))
    except FileNotFoundError:
        return {}


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
    rows: list = field(default_factory=list)   # 원장 거래 줄 (있으면 Report와 같은 계산식 사용)

    @property
    def notional(self):
        return self.c0 * self.cq + self.p0 * self.pq

    def pnl(self, c: float, p: float, on: date | None = None) -> dict:
        """평가손익(원)과 레그 기준 수익률. 금리는 실제 일수/365 (stmon 기존 계산식과 동일)."""
        on = on or date.today()
        rs = (self.c0 - c) / self.c0 + (p - self.p0) / self.p0          # 전략 규칙(손절 판단)용 — 백테스트와 같은 기준, 그대로 유지
        if self.rows:                                                 # 실제 평가손익 = Report와 같은 계산식
            parts = [row_pnl(t, c, p, on) for t in self.rows]
            tot = sum(x['total'] for x in parts)
            return dict(days=max(x['days'] for x in parts), equity=sum(x['equity'] for x in parts),
                        financing=sum(x['financing'] for x in parts), settled=sum(x['settled'] for x in parts),
                        total=tot, ret=tot / self.notional if self.notional else 0.0, ret_strategy=rs)
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
        d.setdefault('rows', []).append(t)
    out = {}
    for a, d in pos.items():
        if d['cq'] <= 0 or d['pq'] <= 0:
            continue
        out[a] = Position(code=a, pref=d['pref'], name=d['name'], entry_date=d['entry_date'],
                          c0=d['cv'] / d['cq'], p0=d['pv'] / d['pq'], cq=d['cq'], pq=d['pq'],
                          bench=d['bench'], sp_short=d['sp_short'], sp_long=d['sp_long'], borrow=d['borrow'], rows=d['rows'])
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
    """청산 거래별 실현손익(고객 관점). 정산 티켓 확정 금액(settlements.json)이 있으면 그 값(페어 단위),
    없으면 Report와 같은 계산식(청산 체결가 + 청산 비용 + 정산 현금). ret = 손익 ÷ 양쪽 진입금액 (Report N%와 같은 기준)"""
    trades = trades if trades is not None else load()
    S = settlements()
    closed = [t for t in trades if t.get('status') == 'Closed' and t.get('exit_date')
              and t.get('common_exit') is not None and t.get('preferred_exit') is not None]
    out, done = [], set()
    for t in closed:
        nm = t.get('pair_name', '')
        if nm in S:
            if nm in done:
                continue
            done.add(nm)
            rows = [x for x in closed if x.get('pair_name') == nm]
            notional = sum(x['common_entry'] * x['common_qty'] + x['preferred_entry'] * x['preferred_qty'] for x in rows)
            entry, exit_ = min(x['entry_date'] for x in rows), max(x['exit_date'] for x in rows)
            tot = float(S[nm]['pnl'])
            out.append(dict(trade_id=t.get('trade_id'), code=t['common_code'], name=nm, entry=entry, leg=notional / 2,
                            exit=exit_, reason=t.get('exit_reason'), days=(date.fromisoformat(exit_) - date.fromisoformat(entry)).days,
                            equity=None, financing=None, settled=None, total=tot, ret=tot / notional if notional else 0.0,
                            source='settlement'))
            continue
        r = row_pnl(t, t['common_exit'], t['preferred_exit'], date.fromisoformat(t['exit_date']))
        notional = t['common_entry'] * t['common_qty'] + t['preferred_entry'] * t['preferred_qty']
        out.append(dict(trade_id=t.get('trade_id'), code=t['common_code'], name=nm, entry=t['entry_date'], leg=notional / 2,
                        exit=t['exit_date'], reason=t.get('exit_reason'), days=r['days'], equity=r['equity'],
                        financing=r['financing'], settled=r['settled'], total=r['total'],
                        ret=r['total'] / notional if notional else 0.0, source='formula'))
    return out