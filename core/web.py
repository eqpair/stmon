"""
웹 출력 — GitHub Pages가 읽는 JSON

data/stock_data.json   : 기존 index.html 형식(호환)
data/trends/{코드}.json : 기존 trade-detail/pair-report 형식(호환) — 이력+현재가로 생성, 네트워크 추가 조회 없음
data/v2_dashboard.json : 새 대시보드(v2.html) — 보유·신호·주문표·손익·수익곡선
"""
from __future__ import annotations
import os
from datetime import datetime
import numpy as np
import pandas as pd
from .data import ROOT, write_json
from .strategy import indicators
from . import report, ledger

D = os.path.join(ROOT, 'data')


def _f(x, nd=2):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


def stock_data(snap: pd.DataFrame, hist: dict):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sig = []
    for r in snap.itertuples():
        dr = hist[r.code].tail(250)
        lr = np.log(dr.C / dr.P)
        sig.append(dict(stock_name=r.name, sz_value=_f(r.z), signal=r.signal, price_a=_f(r.C, 0), price_b=_f(r.P, 0),
                        skew_long=_f(lr.skew()), skew_short=_f(lr.tail(60).skew()), timestamp=now))
    write_json(dict(timestamp=now, last_updated=now, all_signals=sig,
                    divergent_signals=[s for s in sig if s['signal'] == 'IN']), os.path.join(D, 'stock_data.json'))


def trends(hist: dict, names: dict, params_for, days: int = 400):
    os.makedirs(os.path.join(D, 'trends'), exist_ok=True)
    for a, h in hist.items():
        ind = indicators(h.tail(days + 200), params_for(a)).tail(days)
        write_json(dict(stock_code=a, stock_name=names.get(a, a), dates=ind.index.strftime('%Y-%m-%d').tolist(),
                        common_prices=[_f(x, 2) for x in ind.C], preferred_prices=[_f(x, 2) for x in ind.P],
                        discount_rates=[_f(x, 6) for x in ind.dr], sz_values=[_f(x, 4) for x in ind.z],
                        last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                   os.path.join(D, 'trends', f'{a}.json'))


def _orders_records(o):
    if o is None or 'action' not in o:
        return []
    cols = ['code', 'name', 'action', 'z', 'edge', 'qty_C', 'qty_P', 'C', 'P', 'leg_won', 'note', 'pnl_won', 'pnl_ret', 'stop_gap']
    return o[(o.action != '') & (o.action != 'WATCH')][[c for c in cols if c in o]].to_dict('records')


def dashboard(snap: pd.DataFrame, last_orders: pd.DataFrame | None, model: dict, prm, risk, backtest_curve=None,
              live_orders: pd.DataFrame | None = None, market_open: bool = False):
    cols = ['code', 'pref', 'name', 'C', 'P', 'z', 'edge', 'signal', 'armed', 'validated', 'held',
            'entry_date', 'days', 'cq', 'pq', 'c0', 'p0', 'pnl_won', 'pnl_ret', 'ret_rule', 'stop_gap', 'exit']
    pos = snap[snap.held][[c for c in cols if c in snap]]
    watch = snap[(~snap.held) & (snap.z >= snap.z_in - 0.3)].sort_values('z', ascending=False)[
        [c for c in cols if c in snap]]
    eq = pd.read_csv(report.EQUITY).to_dict('records') if os.path.exists(report.EQUITY) else []
    out = dict(updated=datetime.now().isoformat(timespec='seconds'), params=prm.to_dict(),
               risk=dict(capital=risk.capital, slots=risk.slots, gross_limit=risk.gross_limit, liq_frac=risk.liq_frac),
               positions=pos.to_dict('records'), watch=watch.to_dict('records'),
               orders=_orders_records(last_orders), live_orders=_orders_records(live_orders), market_open=market_open,
               live_breadth=(live_orders.attrs.get('breadth') if live_orders is not None else None),
               banned=(bool(live_orders.attrs.get('banned')) if live_orders is not None else False),
               orders_time=(last_orders.attrs.get('time') if last_orders is not None else None),
               model_open=model.get('open', []), equity=eq, realized=ledger.realized(),
               backtest=backtest_curve or {})
    write_json(out, os.path.join(D, 'v2_dashboard.json'))
