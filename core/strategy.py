"""
stmon v2 — 보통주 숏 / 우선주 롱 괴리율 평균회귀 전략 (규칙 정의)

백테스트(backtest.py)와 실시간 신호(signals.py)가 이 파일의 함수만 사용한다.
규칙을 바꾸면 두 곳에 동시에 반영되므로, 검증한 규칙과 실제 매매 규칙이 어긋나지 않는다.

검증 근거 (1997~2026-10, 78쌍, 편도 30bp + 스왑 순비용 연 4%):
  - 계산 기간 90~120일, 진입 Z 2.0~2.25 구간이 훈련(1997-2012)·검증(2013-2026)·최근(2021-) 모두에서 고르게 우수
  - 손절이 없으면 보통주 테마 급등 한 번에 -100% 이상 손실 (계양전기·현대건설 등)
  - 손절 후 Z가 높은 상태에서 곧바로 재진입하면 손실이 반복되므로 Z가 rearm_z 아래로 내려온 뒤에만 재진입
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Params:
    window: int = 120          # 괴리율 평균·표준편차 계산 기간(거래일, 당일 제외)
    z_in: float = 2.0          # 진입: Z >= z_in
    z_out: float = 0.4         # 청산: Z <= z_out
    stop: float = 0.15         # 손절: 페어 누적손익 <= -15% (레그별 진입금액 기준)
    rearm_z: float = 1.0       # 손절·기간청산 뒤 Z가 이 값 아래로 내려와야 재진입 허용
    max_days: int = 0          # 보유기간 제한(거래일). 0 = 사용 안 함
    min_edge: float = 0.03     # 진입 시 기대수익 최소값. log: (Z-z_out)*σ, dr: (Z-z_out)*σ/(1-괴리율)
    fin_rate: float = 0.04     # 스왑 순비용(연). 롱 기준금리+200bp, 숏 기준금리-200bp → 기준금리 상쇄
    cost_bps: float = 30.0     # 편도·레그당 거래비용(수수료+세금+슬리피지)
    min_history: int = 120     # 지표 계산에 필요한 최소 일수
    spread: str = 'log'        # 'log' = ln(C/P) (검증 채택), 'dr' = (C-P)/C (stmon 기존)
    max_premium: float = 1e9    # 우선주/보통주 가격비가 이 값 초과면 신규 진입 금지(우선주 프리미엄 버블 회피)
    rank_by: str = 'edge'      # 슬롯이 부족할 때 우선순위: 'edge' 또는 'z'
    crash_guard: float = 0.5   # 우선주가 60일간 이 비율 이상 하락했으면 진입 금지(0=사용 안 함, 0.5=-50%)
    smooth: int = 1            # 스프레드를 최근 smooth일 평균으로 완화(호가 튐 방지). 1=사용 안 함
    jump_guard: float = 0.31   # 최근 20일 중 한 레그라도 하루 ±31% 넘게 움직였으면 진입 금지(정리매매·이상 데이터)
    max_breadth: float = 1.0   # 거래 가능한 쌍 중 Z>=z_in 비율이 이 값을 넘으면 신규 진입 중단(1.0=사용 안 함)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- 지표
def indicators(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """df: index=날짜, columns=['C'(보통주), 'P'(우선주)] 수정주가.
    반환: dr(괴리율), mu, sd(직전 window일 기준), z, edge"""
    out = df[['C', 'P']].astype(float).copy()
    out['dr'] = (out.C - out.P) / out.C            # 괴리율(표시용)
    x = np.log(out.C / out.P) if p.spread == 'log' else out.dr
    if p.smooth > 1:
        x = x.rolling(p.smooth).mean()
    out['mu'] = x.rolling(p.window).mean().shift(1)
    out['sd'] = x.rolling(p.window).std().shift(1)
    out['z'] = (x - out.mu) / out.sd
    if p.spread == 'log':
        out['edge'] = (out.z - p.z_out) * out.sd            # ln 비율 변화 ≈ 페어 수익률
    else:
        out['edge'] = (out.z - p.z_out) * out.sd / (1.0 - out.dr)
    out.loc[out.P / out.C > p.max_premium, 'edge'] = np.nan   # 프리미엄 버블 쌍은 진입 후보 제외
    if p.crash_guard > 0:
        out.loc[out.P / out.P.shift(60) < 1 - p.crash_guard, 'edge'] = np.nan
    if p.jump_guard > 0:
        jmp = np.maximum(out.C.pct_change().abs(), out.P.pct_change().abs()).rolling(20, min_periods=1).max()
        out.loc[jmp > p.jump_guard, 'edge'] = np.nan
    out['rank'] = out.z if p.rank_by == 'z' else out.edge
    return out


def pair_pnl(c0: float, p0: float, c: float, p: float, days_held: int, prm: Params) -> float:
    """레그별 진입금액 1 기준 누적손익(비용 중 금융비용만 포함). 숏 C + 롱 P."""
    return (c0 - c) / c0 + (p - p0) / p0 - prm.fin_rate * days_held / 252.0


# ---------------------------------------------------------------- 판단
def exit_reason(z: float, pnl: float, days_held: int, prm: Params) -> str | None:
    """보유 중 포지션의 청산 사유. 없으면 None."""
    if z <= prm.z_out:
        return 'TARGET'
    if prm.stop > 0 and pnl <= -prm.stop:
        return 'STOP'
    if prm.max_days > 0 and days_held >= prm.max_days:
        return 'TIME'
    return None


def entry_ok(z: float, edge: float, armed: bool, prm: Params) -> bool:
    if not armed or np.isnan(z) or np.isnan(edge):
        return False
    return z >= prm.z_in and edge >= prm.min_edge


def update_armed(armed: bool, z: float, prm: Params) -> bool:
    """손절·기간청산으로 막힌 쌍은 Z가 rearm_z 아래로 내려오면 다시 진입 가능."""
    if not armed and not np.isnan(z) and z < prm.rearm_z:
        return True
    return armed
