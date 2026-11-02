"""
성과·점검 — 일별 평가 기록, 실현손익, 슬리피지, 규칙 준수, 백테스트 대비

data/v2_equity.csv      : 날짜별 미실현/실현 손익, 보유 수, 총 명목 (15:45에 하루 한 줄)
data/v2_signal_log.csv  : 15:15 주문표에 나온 진입·청산 신호와 그때 가격
"""
from __future__ import annotations
import os
from datetime import date, datetime
import numpy as np
import pandas as pd
from .data import ROOT
from . import ledger

EQUITY = os.path.join(ROOT, 'data', 'v2_equity.csv')
SIGLOG = os.path.join(ROOT, 'data', 'v2_signal_log.csv')


def log_signals(orders: pd.DataFrame):
    act = orders[(orders.action == 'ENTER') | orders.action.str.startswith('EXIT')]
    if not len(act):
        return
    out = act.assign(ts=datetime.now().isoformat(timespec='seconds'), day=date.today().isoformat())
    cols = ['ts', 'day', 'code', 'pref', 'action', 'C', 'P', 'z']
    out[cols].to_csv(SIGLOG, mode='a', header=not os.path.exists(SIGLOG), index=False)


def mark_equity(snap: pd.DataFrame, today: date | None = None):
    """하루 한 줄 기록(같은 날 다시 부르면 덮어씀)."""
    today = today or date.today()
    held = snap[snap.held]
    real = ledger.realized()
    row = dict(date=today.isoformat(), open_pnl=float(held.pnl_won.sum()) if len(held) else 0.0,
               realized_cum=float(sum(r['total'] for r in real)), n_open=int(len(held)),
               gross=float((held.c0 * held.cq + held.p0 * held.pq).sum()) if len(held) else 0.0)
    row['total'] = row['open_pnl'] + row['realized_cum']
    df = pd.read_csv(EQUITY) if os.path.exists(EQUITY) else pd.DataFrame(columns=list(row))
    df = df[df.date != row['date']]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True).sort_values('date')
    df.to_csv(EQUITY, index=False)
    return row


def slippage(trades: list[dict] | None = None) -> pd.DataFrame:
    """신호가격 대비 체결가 차이(bp, +는 불리). 같은 날 같은 코드의 신호와 체결을 짝지음."""
    if not os.path.exists(SIGLOG):
        return pd.DataFrame()
    s = pd.read_csv(SIGLOG, dtype={'code': str, 'pref': str})
    rows = []
    for t in (trades if trades is not None else ledger.load()):
        for kind, d, cpx, ppx in [('ENTER', t.get('entry_date'), t.get('common_entry'), t.get('preferred_entry')),
                                  ('EXIT', t.get('exit_date'), t.get('common_exit'), t.get('preferred_exit'))]:
            if not d or not cpx:
                continue
            m = s[(s.code == t['common_code']) & (s.day == d) & (s.action.str.startswith(kind))]
            if not len(m):
                continue
            g = m.iloc[-1]
            # 진입: 보통주는 높게 팔수록, 우선주는 싸게 살수록 유리 / 청산은 반대
            sc = (g.C - cpx) / g.C * 1e4 if kind == 'ENTER' else (cpx - g.C) / g.C * 1e4
            sp = (ppx - g.P) / g.P * 1e4 if kind == 'ENTER' else (g.P - ppx) / g.P * 1e4
            rows.append(dict(code=t['common_code'], kind=kind, day=d, slip_C_bp=sc, slip_P_bp=sp, slip_bp=(sc + sp) / 2))
    return pd.DataFrame(rows)


def compliance(trades: list[dict] | None = None) -> dict:
    """신호대로 했는지: 신호 없이 한 체결, 체결 안 된 신호"""
    if not os.path.exists(SIGLOG):
        return {}
    s = pd.read_csv(SIGLOG, dtype={'code': str})
    trades = trades if trades is not None else ledger.load()
    fills = {(t['common_code'], t['entry_date'], 'ENTER') for t in trades if t.get('entry_date')}
    fills |= {(t['common_code'], t['exit_date'], 'EXIT') for t in trades if t.get('exit_date')}
    sig = {(r.code, r.day, 'ENTER' if r.action == 'ENTER' else 'EXIT') for r in s.itertuples()}
    since = s.day.min()
    fills = {f for f in fills if f[1] >= since}
    return dict(since=since, signals=len(sig), fills=len(fills),
                missed=sorted(sig - fills), unsignaled=sorted(fills - sig))


def summary(capital: float | None) -> str:
    real = ledger.realized()
    L = ['📈 <b>stmon 성과 리포트</b>']
    if os.path.exists(EQUITY):
        e = pd.read_csv(EQUITY)
        if len(e):
            last = e.iloc[-1]
            L.append(f"누적 손익 {last.total / 1e4:+,.0f}만원 (실현 {last.realized_cum / 1e4:+,.0f} / 평가 {last.open_pnl / 1e4:+,.0f})"
                     + (f" · 자본 대비 {last.total / capital:+.1%}" if capital else ''))
            if capital and len(e) > 1:
                eq = capital + e.total
                dd = (eq / eq.cummax() - 1).min()
                L.append(f"기록 {len(e)}일 · 최대낙폭 {dd:.1%}")
    if real:
        r = pd.DataFrame(real)
        L.append(f"청산 {len(r)}건 · 승률 {(r.total > 0).mean():.0%} · 평균 {r.ret.mean():+.1%} · 최악 {r.ret.min():+.1%}")
    sl = slippage()
    if len(sl):
        L.append(f"슬리피지(신호가 대비) 평균 {sl.slip_bp.mean():+.0f}bp ({len(sl)}건, 가정 30bp)")
    c = compliance()
    if c:
        L.append(f"규칙 준수: 신호 {c['signals']}건 중 미체결 {len(c['missed'])} · 신호 없는 체결 {len(c['unsignaled'])}")
    return '\n'.join(L)
