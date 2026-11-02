"""
stmon v2 백테스트 엔진 — modules/strategy.py 규칙을 그대로 사용하는 포트폴리오 시뮬레이터
실행은 저장소 최상위의 backtest.py 로:
    python3 backtest.py                 # 기본 파라미터, 동시보유 10쌍, 같은 날 체결
    python3 backtest.py --lag 1         # 전일 판단 → 당일 체결(보수적)
    python3 backtest.py --window 90 --z_in 2.25

자본 모델:
  slots=K : 자본을 K칸으로 나누고, 한 칸에 레그당 1/K 명목(숏 C 1/K + 롱 P 1/K).
            빈 칸이 생기면 그날 진입 조건을 만족하는 쌍 중 기대수익(edge)이 큰 순서로 채움.
  slots=0 : 쌍마다 자본 1/(그날 거래 가능한 쌍 수)를 고정 배정(진입 경쟁 없음).
체결: 신호가 난 날 종가에 체결(장 마감 직전 체결 가정). 비용은 레그·편도마다 cost_bps.
"""
from __future__ import annotations
import argparse, glob, os, json
from dataclasses import replace
import numpy as np
import pandas as pd
from .strategy import Params, indicators, pair_pnl, exit_reason, entry_ok, update_armed

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 저장소 최상위

# 공매도 금지 기간: 이 기간에는 신규 진입하지 않음(실제로도 매매하지 않았음). 보유분 청산은 허용.
SHORT_BANS = [('2008-10-01', '2009-05-31'), ('2011-08-10', '2011-11-09'),
              ('2020-03-16', '2021-05-02'), ('2023-11-06', '2025-03-30')]


def load_history(folder=os.path.join(HERE, 'data', 'history'), min_rows=400):
    data = {}
    for f in sorted(glob.glob(os.path.join(folder, '*.csv'))):
        a, b = os.path.basename(f)[:-4].split('_')
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        df = df[(df.C > 0) & (df.P > 0)].dropna()
        if len(df) >= min_rows:
            data[a] = df
    return data


def simulate(data: dict, prm: Params, slots: int = 10, start='1997-01-01', warmup_days=400,
             exec_lag: int = 0, return_state: bool = False, blackout=None, pair_params: dict | None = None,
             entry_block=None):
    """exec_lag=0: t일 종가로 판단·체결(장 마감 직전 판단 가정)
       exec_lag=1: t-1일 종가로 판단, t일 종가 체결(가장 보수적)"""
    tb = prm.cost_bps / 1e4
    L = int(exec_lag)
    if blackout is None:
        blackout = SHORT_BANS
    PP = {k: (pair_params or {}).get(k, prm) for k in data}       # 쌍별 파라미터(없으면 공통)
    ind = {k: indicators(v, PP[k]) for k, v in data.items()}
    cal = sorted(set().union(*[set(v.index) for v in ind.values()]))
    cal = pd.DatetimeIndex(cal)
    cal = cal[cal >= pd.Timestamp(start)]
    A = {}
    for k, d in ind.items():
        r = d.reindex(cal)
        native = r.C.notna().values
        r[['C', 'P']] = r[['C', 'P']].ffill()
        tradable_from = d.index[0] + pd.Timedelta(days=warmup_days)
        in_span = (cal >= d.index[0]) & (cal <= d.index[-1])      # 데이터가 끝난 쌍은 거래 불가
        A[k] = dict(C=r.C.values, P=r.P.values, nat=native,
                    z=np.where(native, r.z.values, np.nan),
                    edge=np.where(native, r.edge.values, np.nan),
                    rank=np.where(native, r['rank'].values, np.nan),
                    live=(cal >= tradable_from) & in_span & ~np.isnan(r.C.values))
    keys = list(A)
    blk = np.zeros(len(cal), bool)
    for a_, b_ in blackout:
        blk |= (cal >= pd.Timestamp(a_)) & (cal <= pd.Timestamp(b_))
    if entry_block is not None:                 # 국면 필터: True인 날(판단일 기준)은 신규 진입 없음
        eb = entry_block.reindex(cal).fillna(False).values.astype(bool)
    else:
        eb = np.zeros(len(cal), bool)
    pos = {}
    armed = {k: True for k in keys}
    daily = np.zeros(len(cal))
    nopen = np.zeros(len(cal), int)
    trades = []

    def close(k, t, why):
        ps = pos.pop(k)
        a = A[k]
        cum = pair_pnl(ps['c0'], ps['p0'], a['C'][t], a['P'][t], t - ps['i0'], PP[k])
        trades.append(dict(pair=k, entry=cal[ps['i0']], exit=cal[t], days=t - ps['i0'], ret=cum - 4 * tb, reason=why))
        if why in ('STOP', 'TIME', 'DATA_END'):
            armed[k] = False
        return ps['w'] * 2 * tb

    for t in range(max(1, L), len(cal)):
        s = t - L                                   # 판단 시점
        n_live = sum(A[k]['live'][t] for k in keys)
        unit = (1.0 / slots) if slots > 0 else (1.0 / max(n_live, 1))
        pnl_t = 0.0
        # 1) 보유 포지션 평가(t일 가격) 후 판단(s일 정보) → t일 체결
        for k in list(pos):
            a, ps = A[k], pos[k]
            pnl_t += ps['w'] * ((a['C'][t - 1] - a['C'][t]) / ps['c0'] + (a['P'][t] - a['P'][t - 1]) / ps['p0']
                                - prm.fin_rate / 252)
            if not a['live'][t] and t > 0 and cal[t] > cal[0]:
                if not (cal[t] <= cal[-1] and a['nat'][t]):
                    if not np.any(a['nat'][t:]):          # 데이터 끝: 마지막 가격으로 정리
                        pnl_t -= close(k, t, 'DATA_END')
                        continue
            if s < ps['i0'] or not a['nat'][s] or not a['nat'][t]:
                continue
            cum = pair_pnl(ps['c0'], ps['p0'], a['C'][s], a['P'][s], s - ps['i0'], PP[k])
            z = a['z'][s]
            why = exit_reason(z if np.isfinite(z) else np.inf, cum, s - ps['i0'], PP[k])
            if why:
                pnl_t -= close(k, t, why)
        # 2) 재진입 허용 갱신(s일 정보)
        for k in keys:
            armed[k] = update_armed(armed[k], A[k]['z'][s], PP[k])
        # 3) 신규 진입: s일 신호, t일 체결
        zs = [A[k]['z'][s] for k in keys if A[k]['live'][s] and np.isfinite(A[k]['z'][s])]
        breadth = np.mean([A[k]['z'][s] >= PP[k].z_in for k in keys if A[k]['live'][s] and np.isfinite(A[k]['z'][s])]) if zs else 0.0
        cands = [(A[k]['rank'][s], k) for k in keys
                 if k not in pos and A[k]['live'][s] and A[k]['live'][t] and A[k]['nat'][t]
                 and entry_ok(A[k]['z'][s], A[k]['edge'][s], armed[k], PP[k])]
        cands.sort(reverse=True)
        if breadth > prm.max_breadth or blk[t] or eb[s]:
            cands = []
        free = (slots - len(pos)) if slots > 0 else len(cands)
        for e, k in cands[:max(free, 0)]:
            pos[k] = dict(i0=t, c0=A[k]['C'][t], p0=A[k]['P'][t], w=unit)
            pnl_t -= unit * 2 * tb
        daily[t] = pnl_t
        nopen[t] = len(pos)
    for k, ps in pos.items():
        t = len(cal) - 1
        trades.append(dict(pair=k, entry=cal[ps['i0']], exit=pd.NaT, days=t - ps['i0'],
                           ret=pair_pnl(ps['c0'], ps['p0'], A[k]['C'][t], A[k]['P'][t], t - ps['i0'], prm),
                           reason='OPEN'))
    out = (pd.Series(daily, index=cal), pd.DataFrame(trades), pd.Series(nopen, index=cal))
    if return_state:
        return out + (dict(armed=armed, open=sorted(pos), date=str(cal[-1].date())),)
    return out


def stats(r: pd.Series, T: pd.DataFrame | None = None, a=None, b=None):
    x = r[a:b]
    eq = (1 + x).cumprod()
    yrs = len(x) / 252
    o = dict(CAGR=eq.iloc[-1] ** (1 / yrs) - 1, vol=x.std() * np.sqrt(252),
             sharpe=x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0,
             MDD=(eq / eq.cummax() - 1).min())
    if T is not None and len(T):
        t = T[(T.entry >= pd.Timestamp(a or '1900')) & (T.entry <= pd.Timestamp(b or '2100'))]
        c = t[t.reason != 'OPEN']
        o.update(trades=len(t), win=(c.ret > 0).mean(), avg=c.ret.mean(), worst=t.ret.min(),
                 stops=(t.reason == 'STOP').mean(), med_days=c.days.median())
    return o


PERIODS = [('전체', '1997', '2026-12-31'), ('1997-2007', '1997', '2007-12-31'),
           ('2008-2012', '2008', '2012-12-31'), ('2013-2020', '2013', '2020-12-31'),
           ('2021-', '2021', '2026-12-31')]


def report(r, T, title=''):
    rows = [dict(period=n, **stats(r, T, a, b)) for n, a, b in PERIODS]
    df = pd.DataFrame(rows).set_index('period')
    pct = ['CAGR', 'vol', 'MDD', 'win', 'avg', 'worst', 'stops']
    show = df.copy()
    for c in pct:
        if c in show:
            show[c] = show[c].map(lambda v: f'{v:.1%}')
    show['sharpe'] = show['sharpe'].map(lambda v: f'{v:.2f}')
    print(f'\n== {title}\n' + show.to_string())
    return df
