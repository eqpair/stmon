"""
판단 계층 — 매 주기 스냅샷(장중 감시) + 15:15 주문표

규칙은 core/strategy.py(백테스트와 공용). 재진입 금지 상태는 확정 종가로 백테스트를 재생해 얻고(model_state),
장부의 실제 손절 청산도 반영한다. 장중 값은 저장하지 않는다.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
import numpy as np
import pandas as pd
from .strategy import Params, indicators, pair_pnl, exit_reason, entry_ok, update_armed
from .engine import simulate
from . import ledger

VALIDATED_MIN_ROWS = 750      # 이보다 짧은 이력은 신호만 표시, 신규 진입 제외


@dataclass
class Risk:
    capital: float | None = None    # 총 운용자금(원). 있어야 수량 계산
    slots: int = 10                 # 동시 보유 쌍 수 → 레그당 명목 = capital/slots
    gross_limit: float = 2.0        # 총 명목(숏+롱) / 자본 상한
    liq_frac: float = 0.10          # 레그 금액 ≤ 해당 종목 20일 평균 거래대금 × liq_frac
    stop_warn: float = 0.10         # 장중 손익이 -10% 이하이면 손절선 접근 알림
    bench_rate: float = 2.5         # 신규 진입 기록 시 기본 기준금리(%)
    sp_short: float = -202          # 기본 숏 스프레드(bp)
    sp_long: float = 200            # 기본 롱 스프레드(bp)
    leg_min: float | None = None    # 레그 최소 금액(원)
    leg_max: float | None = None    # 레그 최대 금액(원)
    adv_mult: float = 1.5           # 레그 ≤ 20일 평균 거래대금 × adv_mult
    day_frac: float = 0.3           # 하루 체결 가능 = 20일 평균 거래대금 × day_frac


def in_blackout(d: date, blackout) -> bool:
    return any(pd.Timestamp(a) <= pd.Timestamp(d) <= pd.Timestamp(b) for a, b in blackout)


def model_state(hist: dict, prm: Params, slots: int, blackout, pair_params: dict, entry_block=None):
    """확정 종가로 백테스트 재생 → (state{'armed','open','date'}, 일별수익률 Series)"""
    bt = {k: v for k, v in hist.items() if len(v) >= 400}
    r, _, _, st = simulate(bt, prm, slots=slots, return_state=True, start='2015-01-01',
                           blackout=blackout, pair_params=pair_params, entry_block=entry_block)
    return st, r


def actual_stop_blocks(hist: dict, prm: Params, trades: list[dict]) -> dict:
    """장부의 손절 청산(exit_reason=STOP 또는 전략손익 <= -stop) 뒤 Z가 rearm_z 아래로 내려온 적 없는 쌍"""
    last = {}
    for t in trades:
        if t.get('status') != 'Closed' or not t.get('exit_date') or not t.get('common_exit'):
            continue
        a = t['common_code']
        if a not in hist:
            continue
        h = hist[a]
        days = int(((h.index > pd.Timestamp(t['entry_date'])) & (h.index <= pd.Timestamp(t['exit_date']))).sum())
        r = pair_pnl(t['common_entry'], t['preferred_entry'], t['common_exit'], t['preferred_exit'], days, prm)
        if str(t.get('exit_reason') or '').upper() == 'STOP' or r <= -prm.stop:
            last[a] = max(last.get(a, ''), t['exit_date'])
    out = {}
    for a, xd in last.items():
        z = indicators(hist[a], prm).z
        if not (z[z.index > pd.Timestamp(xd)] < prm.rearm_z).any():
            out[a] = xd
    return out


def snapshot(hist: dict, live: dict[str, float], pairs: list[tuple[str, str]], names: dict, prm: Params,
             pair_params: dict, armed: dict, positions: dict, today: date | None = None) -> pd.DataFrame:
    """쌍별 현재 상태. live = {종목코드: 현재가}. 확정 이력 마지막 날이 오늘이면 그 행을 현재가로 대체."""
    today = today or date.today()
    newest = max(v.index[-1] for v in hist.values())
    rows = []
    for a, b in pairs:
        if a not in hist:
            continue
        P_ = pair_params.get(a, prm)
        h = hist[a].tail(max(P_.window + 80, 400)).copy()
        n_conf = len(hist[a])
        stale = bool(np.busday_count(hist[a].index[-1].date(), newest.date()) >= 2)
        c, p = live.get(a), live.get(b)
        has_live = bool(c and p) and not stale
        if has_live:
            h.loc[pd.Timestamp(today)] = [c, p]
            h = h.sort_index()
        d = indicators(h, P_).iloc[-1]
        ar = update_armed(armed.get(a, True), d.z, P_)
        sig = 'IN' if d.z >= P_.z_in else ('OUT' if d.z <= P_.z_out else 'CHK')
        row = dict(code=a, pref=b, name=names.get(a, a), date=str(h.index[-1].date()), live=has_live,
                   C=float(d.C), P=float(d.P), dr=float(d.dr), z=float(d.z), edge=float(d.edge),
                   rank=float(d['rank']), signal=sig, armed=bool(ar), validated=n_conf >= VALIDATED_MIN_ROWS,
                   stale=stale, z_in=P_.z_in, z_out=P_.z_out, held=a in positions)
        if a in positions:
            ps = positions[a]
            tdays = int((h.index > pd.Timestamp(ps.entry_date)).sum())
            r_rule = pair_pnl(ps.c0, ps.p0, d.C, d.P, tdays, P_)          # 규칙 판단용(백테스트와 동일 기준)
            m = ps.pnl(d.C, d.P, today)                                   # 실제 평가손익(원)
            why = exit_reason(d.z if np.isfinite(d.z) else np.inf, r_rule, tdays, P_)
            row.update(entry_date=ps.entry_date, days=tdays, ret_rule=r_rule, pnl_won=m['total'],
                       pnl_ret=m['ret'], financing=m['financing'], cq=ps.cq, pq=ps.pq, c0=ps.c0, p0=ps.p0,
                       stop_gap=r_rule + P_.stop, exit=why)
        rows.append(row)
    return pd.DataFrame(rows)


def max_leg(liq: dict, code: str, risk: Risk):
    """종목별 진입 최대금액 = min(최대 레그, 보통주·우선주 중 작은 20일 평균 거래대금 × 배수). 데이터 없으면 None"""
    if not risk.leg_max:
        return None
    x = liq.get(code) or {}
    v = [a for a in (x.get('C'), x.get('P')) if a]
    return float(min(risk.leg_max, min(v) * risk.adv_mult)) if v else None


def day_leg(liq: dict, code: str, risk: Risk):
    """하루에 넣을 수 있는 한쪽 금액 = min(최대 레그, 보통주·우선주 중 작은 20일 평균 거래대금 × day_frac)"""
    ml = max_leg(liq, code, risk)
    x = liq.get(code) or {}
    v = [a for a in (x.get('C'), x.get('P')) if a]
    return float(min(ml, min(v) * risk.day_frac)) if (v and ml is not None) else None


def orders(snap: pd.DataFrame, prm: Params, risk: Risk, blackout, liq: dict, today: date | None = None,
           vol_ratio: float | None = None, vol_block: float | None = None) -> pd.DataFrame:
    """15:15 주문표. action: EXIT_TARGET/EXIT_STOP/EXIT_TIME, HOLD, ENTER, WAIT_SLOT, BLOCKED_BAN, BLOCKED_LIQ, WATCH"""
    today = today or date.today()
    df = snap.copy()
    df['action'] = ''
    held = df.held
    df.loc[held, 'action'] = df.loc[held, 'exit'].map(lambda w: f'EXIT_{w}' if isinstance(w, str) else 'HOLD')
    ok = (~held) & df.validated & ~df.stale & df.armed & df.apply(
        lambda r: entry_ok(r.z, r.edge, r.armed, Params(z_in=r.z_in, z_out=r.z_out, min_edge=prm.min_edge)), axis=1)
    df.loc[ok, 'action'] = 'CAND'
    df.loc[(~held) & (df.action == '') & (df.z >= df.z_in), 'action'] = 'WATCH'
    # 공통 필터
    lv = df[df.validated & ~df.stale & np.isfinite(df.z)]
    breadth = float((lv.z >= lv.z_in).mean()) if len(lv) else 0.0
    banned = in_blackout(today, blackout)
    if banned:
        df.loc[df.action == 'CAND', 'action'] = 'BLOCKED_BAN'
    elif breadth > prm.max_breadth:
        df.loc[df.action == 'CAND', 'action'] = 'WATCH'
    vol_hot = bool(vol_block and vol_ratio is not None and vol_ratio == vol_ratio and vol_ratio > vol_block)
    if vol_hot:                                  # 시장 고변동: 신규 진입 쉼
        df.loc[df.action == 'CAND', 'action'] = 'BLOCKED_VOL'
    # 종목별 최대 레그(거래대금 기준)
    ML = {c: max_leg(liq, c, risk) for c in df.code}
    DL = {c: day_leg(liq, c, risk) for c in df.code}
    if risk.leg_max:
        for i in df.index[df.action == 'CAND']:
            ml = ML.get(df.at[i, 'code'])
            if ml is None:
                continue
            if ml < (risk.leg_min or 0):
                df.at[i, 'action'] = 'BLOCKED_LIQ'
                df.at[i, 'note'] = f'종목당 최대 {ml / 1e4:,.0f}만 < {risk.leg_min / 1e4:,.0f}만'
                continue
            df.at[i, 'leg_won'] = ml
            df.at[i, 'day_won'] = DL.get(df.at[i, 'code'])
            df.at[i, 'qty_C'] = int(ml // df.at[i, 'C'])
            df.at[i, 'qty_P'] = int(ml // df.at[i, 'P'])
    # 수량·유동성(자본 기준, 최대 레그 미설정 시)
    unit = (risk.capital / risk.slots) if risk.capital else None
    if unit and not risk.leg_max:
        for i in df.index[df.action == 'CAND']:
            lc, lp = (liq.get(df.at[i, 'code']) or {}).get('C'), (liq.get(df.at[i, 'code']) or {}).get('P')
            cap = min([x * risk.liq_frac for x in (lc, lp) if x] or [unit])
            leg = min(unit, cap)
            if leg < unit * 0.3:
                df.at[i, 'action'] = 'BLOCKED_LIQ'
                df.at[i, 'note'] = f'거래대금 부족(레그 한도 {leg / 1e6:.0f}백만원)'
                continue
            df.at[i, 'leg_won'] = leg
            df.at[i, 'qty_C'] = int(leg // df.at[i, 'C'])
            df.at[i, 'qty_P'] = int(leg // df.at[i, 'P'])
    # 슬롯·총노출
    n_keep = int((df.action == 'HOLD').sum())
    free = max(risk.slots - n_keep, 0)
    if unit:
        gross_now = float((df.loc[df.action == 'HOLD', 'c0'] * df.loc[df.action == 'HOLD', 'cq']).sum()
                          + (df.loc[df.action == 'HOLD', 'p0'] * df.loc[df.action == 'HOLD', 'pq']).sum())
        room = risk.capital * risk.gross_limit - gross_now
        free = min(free, max(int(room // (2 * unit)), 0))
    cand = df[df.action == 'CAND'].sort_values('rank', ascending=False)
    df.loc[cand.index[:free], 'action'] = 'ENTER'
    df.loc[df.action == 'CAND', 'action'] = 'WAIT_SLOT'
    df.attrs['max_leg'] = {c: v for c, v in ML.items() if v is not None}
    df.attrs['day_leg'] = {c: v for c, v in DL.items() if v is not None}
    df.attrs.update(breadth=breadth, banned=banned, free=free, vol_ratio=vol_ratio, vol_block=vol_block, vol_hot=vol_hot)
    return df


def fmt_orders(df: pd.DataFrame, prm: Params, model_open=None) -> str:
    t = datetime.now()
    L = [f'📋 <b>stmon 주문표 {t:%m-%d %H:%M}</b>  (진입 Z≥{prm.z_in} / 청산 Z≤{prm.z_out} / 손절 {prm.stop:.0%})']
    _v, _vb = df.attrs.get('vol_ratio'), df.attrs.get('vol_block')
    _vt = f"{_v:.2f}배" if isinstance(_v, (int, float)) and _v == _v else '-'
    if df.attrs.get('banned'):
        L.append('⛔ <b>신규 진입 쉼</b> · 공매도 금지 기간')
    elif df.attrs.get('vol_hot'):
        L.append(f'🌪 <b>신규 진입 쉼</b> · 시장 변동성 {_vt} > 기준 {_vb}배')
    else:
        L.append(f'✅ <b>진입 가능</b> · 시장 변동성 {_vt} (기준 {_vb}배)')
    ex = df[df.action.str.startswith('EXIT')]
    for _, r in ex.iterrows():
        L.append(f"🔴 <b>청산</b> {r['name']}  [{r.action[5:]}]\n    보통주 {int(r.cq)}주 매수상환 · 우선주 {int(r.pq)}주 매도"
                 f"  | Z {r.z:+.2f} · 손익 {r.pnl_won / 1e4:+,.0f}만원 ({r.pnl_ret:+.1%})")
    en = df[df.action == 'ENTER']
    for _, r in en.iterrows():
        q = (f"\n    종목당 {r.leg_won / 1e4:,.0f}만원 (하루 {(r.get('day_won') or 0) / 1e4:,.0f}만원) · 보통주 {int(r.qty_C)}주 공매도(~{r.C:,.0f}) · 우선주 {int(r.qty_P)}주 매수(~{r.P:,.0f})"
             if 'qty_C' in r and pd.notna(r.get('qty_C')) else '')
        L.append(f"🟢 <b>진입</b> {r['name']}  Z {r.z:+.2f} · 기대 {r.edge:.1%}{q}")
    for _, r in df[df.action == 'HOLD'].iterrows():
        L.append(f"⚪ 보유 {r['name']}  Z {r.z:+.2f} · {r.pnl_won / 1e4:+,.0f}만원 ({r.pnl_ret:+.1%}) · 손절까지 {r.stop_gap:.1%}")
    for act, label in [('WAIT_SLOT', '⏳ 슬롯 부족'), ('BLOCKED_BAN', '⛔ 공매도 금지기간'), ('BLOCKED_LIQ', '💧 거래대금 부족'), ('BLOCKED_VOL', '🌪 시장 고변동(신규 진입 쉼)')]:
        x = df[df.action == act]
        if len(x):
            L.append(f"{label}: " + ', '.join(x['name']))
    if len(ex) == 0 and len(en) == 0:
        L.append('오늘 주문 없음')
    if model_open is not None:
        held = set(df.loc[df.held, 'code'])
        if set(model_open) != held:
            L.append(f"(참고) 모델 보유 {len(model_open)}쌍 / 실제 보유 {len(held)}쌍")
    L.append('체결 후: /in 코드 보통주수량@가격 우선주수량@가격  ·  /out 코드 보통주가격 우선주가격 [STOP]')
    return '\n'.join(L)
