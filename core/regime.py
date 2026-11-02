"""
시장 국면 — 보유 종목 보통주 동일가중 지수의 단기 변동성 배수

검증(1997~2026): 시장 20일 변동성이 직전 1년 중앙값의 2.0배를 넘는 날 신규 진입을 쉬면
최대낙폭 −26%→−20%(같은 날 체결), −39%→−28%(보수적), 2021년 이후 Sharpe 0.71→0.81, 0.38→0.82.
원웨이 급등·급락 회피(60일 ±15%, 효율비)는 오히려 성과를 낮춰 채택하지 않음.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

MIN_ROWS = 400   # 백테스트와 같은 범위(장기 이력 있는 쌍)로 지수 구성


def _panel(hist: dict) -> pd.DataFrame:
    return pd.DataFrame({k: v.C for k, v in hist.items() if len(v) >= MIN_ROWS}).sort_index()


def vol_ratio_from_panel(C: pd.DataFrame) -> pd.Series:
    r = C.pct_change(fill_method=None)
    r = r.where(r.abs() < 0.3)                     # 이상치(정리매매·데이터 오류) 제외
    m = r.mean(axis=1).fillna(0)
    v20 = m.rolling(20).std()
    return v20 / v20.rolling(250).median()


def vol_ratio_series(hist: dict) -> pd.Series:
    """일별 변동성 배수(그날 종가까지의 정보)"""
    return vol_ratio_from_panel(_panel(hist))


def vol_ratio_now(hist: dict, live: dict | None = None, today=None) -> float:
    """오늘 현재가를 붙여 계산한 변동성 배수. live = {보통주코드: 현재가}"""
    C = _panel(hist).tail(320)
    if live:
        t = pd.Timestamp(today or pd.Timestamp.now().normalize())
        row = {k: live.get(k) for k in C.columns}
        if any(v for v in row.values()) and t > C.index[-1]:
            C.loc[t] = [row[k] if row[k] else np.nan for k in C.columns]
    s = vol_ratio_from_panel(C).dropna()
    return float(s.iloc[-1]) if len(s) else float('nan')
