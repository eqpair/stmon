"""
stmon v2 매매 신호 — modules/strategy.py 규칙으로 오늘 할 일을 계산 (main.py가 15:15에 자동 호출)

수동 실행:
  python3 -m modules.v2                  # 이력 갱신 없이, 현재가로 신호 계산·출력
  python3 -m modules.v2 --update         # 네이버에서 최근 일봉을 받아 data/history 갱신 후 계산
  python3 -m modules.v2 --no-live        # 현재가 대신 마지막 확정 종가로 계산

판단 기준은 백테스트와 같다: 장 마감 직전(15:15) 현재가를 종가로 보고 계산.
보유 현황은 data/pair-trades.json(status=Open)을 그대로 읽는다.
손절 뒤 재진입 대기 상태는 상태 파일 없이 매번 확정 종가 이력으로 백테스트를 다시 돌려 계산하고,
pair-trades.json의 실제 손절 청산도 반영한다.
결과: data/v2_signals.json (웹용), data/v2_signal_log.csv (신호가격 기록 → 실제 체결가와 비교용)
"""
from __future__ import annotations
import argparse, json, os, sys, time, re, urllib.request
from datetime import datetime, date
import numpy as np
import pandas as pd
from .strategy import Params, indicators, pair_pnl, exit_reason, entry_ok, update_armed
from .engine import load_history, simulate, SHORT_BANS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # 저장소 최상위
HIST = os.path.join(HERE, 'data', 'history')
OUT = os.path.join(HERE, 'data', 'v2_signals.json')
LOG = os.path.join(HERE, 'data', 'v2_signal_log.csv')
TRADES = os.environ.get('STMON_TRADES', os.path.join(HERE, 'data', 'pair-trades.json'))
UA = {'User-Agent': 'Mozilla/5.0'}

# 백테스트 이력(1995~)이 없어 장기 검증을 못 한 쌍: 신호는 보여주되 신규 진입 후보에서는 제외
UNVALIDATED_MIN_ROWS = 750


# ---------------------------------------------------------------- 데이터
def _get(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')


def naver_daily(code: str, count: int = 40) -> pd.Series:
    """네이버 fchart 일봉 종가(수정주가)."""
    txt = _get(f'https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0')
    rows = re.findall(r'data="([^"]+)"', txt)
    s = {}
    for r in rows:
        f = r.split('|')
        if len(f) >= 5 and float(f[4]) > 0:
            s[pd.Timestamp(f[0])] = float(f[4])
    return pd.Series(s).sort_index()


def naver_now(code: str) -> float | None:
    try:
        j = json.loads(_get(f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}', 5))
        v = j['result']['areas'][0]['datas'][0].get('nv')
        return float(v) if v and float(v) > 0 else None
    except Exception:
        return None


def update_history(a: str, b: str, today: date) -> str:
    """이력 CSV에 최근 일봉을 덧붙인다. 겹치는 날 가격이 다르면(액면분할·감자 등) 과거 전체를 비율로 재조정.
    오늘 날짜(장중 미확정 봉)는 저장하지 않는다."""
    f = os.path.join(HIST, f'{a}_{b}.csv')
    h = pd.read_csv(f, index_col=0, parse_dates=True)
    c, p = naver_daily(a), naver_daily(b)
    new = pd.DataFrame({'C': c, 'P': p}).dropna()
    if len(new) and len(new.index.intersection(h.index)) == 0:      # 공백이 생기면 더 길게 받아 다시 시도
        c, p = naver_daily(a, 600), naver_daily(b, 600)
        new = pd.DataFrame({'C': c, 'P': p}).dropna()
        if len(new.index.intersection(h.index)) == 0:
            raise RuntimeError('이력과 겹치는 날짜가 없어 이어붙일 수 없음(수동 확인 필요)')
    # 장 마감 확정(15:40) 전에는 오늘 봉을 저장하지 않음 (미확정 봉 = 0 또는 장중가)
    after_close = datetime.now().hour * 60 + datetime.now().minute >= 15 * 60 + 40
    new = new[(new.index.date < today) | (after_close & (new.index.date == today))]
    if new.empty:
        return 'no data'
    ov = new.index.intersection(h.index)
    msg = 'ok'
    if len(ov):
        last = ov[-1]
        k = new.loc[last] / h.loc[last]
        if (abs(k - 1) > 0.002).any():          # 기업 이벤트로 수정주가 재계산됨
            h = h * k
            msg = f'rescaled C×{k.C:.4f} P×{k.P:.4f}'
    h = pd.concat([h[h.index < new.index[0]], new]).sort_index()
    h = h[~h.index.duplicated(keep='last')]
    tmp = f + '.tmp'
    h.round(4).to_csv(tmp)
    os.replace(tmp, f)
    return msg


# ---------------------------------------------------------------- 보유
def open_positions():
    """pair-trades.json에서 보유 중(Open) 페어. 같은 보통주 코드가 여러 건이면 수량가중 평균가로 합침."""
    try:
        tr = json.load(open(TRADES, encoding='utf-8'))
    except Exception:
        return {}
    pos = {}
    for t in tr:
        if t.get('status') != 'Open':
            continue
        a = t['common_code']
        d = pos.setdefault(a, dict(name=t.get('pair_name', a), entry_date=t['entry_date'], cq=0, pq=0, cv=0.0, pv=0.0))
        d['entry_date'] = min(d['entry_date'], t['entry_date'])
        d['cq'] += t['common_qty']; d['pq'] += t['preferred_qty']
        d['cv'] += t['common_entry'] * t['common_qty']; d['pv'] += t['preferred_entry'] * t['preferred_qty']
    for a, d in pos.items():
        d['c0'] = d['cv'] / d['cq'] if d['cq'] else np.nan
        d['p0'] = d['pv'] / d['pq'] if d['pq'] else np.nan
    return pos


def actual_stop_blocks(prm: Params, hist: dict) -> dict:
    """pair-trades.json의 청산 거래 중 손절(exit_reason='STOP'이거나 청산 손익 <= -stop)이 있고,
    그 뒤 확정 종가 Z가 한 번도 rearm_z 아래로 내려오지 않은 쌍 → 재진입 금지."""
    try:
        tr = json.load(open(TRADES, encoding='utf-8'))
    except Exception:
        return {}
    last = {}
    for t in tr:
        if t.get('status') != 'Closed' or not t.get('exit_date') or not t.get('common_exit') or not t.get('preferred_exit'):
            continue
        a = t['common_code']
        if a not in hist:
            continue
        h = hist[a]
        days = int(((h.index > pd.Timestamp(t['entry_date'])) & (h.index <= pd.Timestamp(t['exit_date']))).sum())
        pnl = pair_pnl(t['common_entry'], t['preferred_entry'], t['common_exit'], t['preferred_exit'], days, prm)
        is_stop = str(t.get('exit_reason', '')).upper() == 'STOP' or pnl <= -prm.stop
        if is_stop and (a not in last or t['exit_date'] > last[a]):
            last[a] = t['exit_date']
    out = {}
    for a, xd in last.items():
        z = indicators(hist[a], prm).z
        after = z[z.index > pd.Timestamp(xd)]
        if not (after < prm.rearm_z).any():
            out[a] = xd
    return out


# ---------------------------------------------------------------- 신호
def update_all_history(today: date | None = None):
    """data/history 전체를 네이버 일봉으로 갱신. 반환: [(코드, 결과)]"""
    today = today or date.today()
    log = []
    for fn in sorted(f[:-4] for f in os.listdir(HIST) if f.endswith('.csv')):
        a, b = fn.split('_')
        try:
            log.append((a, update_history(a, b, today)))
        except Exception as e:
            log.append((a, f'update fail {e}'))
        time.sleep(0.15)
    return log


def in_blackout(d: date, blackout) -> bool:
    return any(pd.Timestamp(a) <= pd.Timestamp(d) <= pd.Timestamp(b) for a, b in blackout)


def compute(prm: Params, live=True, slots=10, capital=None, pair_params=None, blackout=None):
    """live: True=네이버 현재가 조회 / dict{보통주코드: (보통주가, 우선주가)}=주어진 가격 사용 / None·False=확정 종가만"""
    today = date.today()
    blackout = SHORT_BANS if blackout is None else blackout
    pair_params = pair_params or {}
    files = sorted(f[:-4] for f in os.listdir(HIST) if f.endswith('.csv'))
    held = open_positions()
    # 1) 확정 종가 이력으로 백테스트 재생 → 재진입 대기 상태(armed)와 모델 보유 목록
    hist_all = load_history(HIST, min_rows=prm.min_history + 2)          # 신호 표시용(짧은 이력 쌍 포함)
    hist_bt = {k: v for k, v in hist_all.items() if len(v) >= 400}          # 백테스트와 같은 범위로 재생
    _, _, _, model = simulate(hist_bt, prm, slots=slots, return_state=True, start='2015-01-01',
                              blackout=blackout, pair_params=pair_params)
    hist = hist_all
    armed = dict(model['armed'])
    for k, why in actual_stop_blocks(prm, hist).items():      # 실제 손절 기록도 재진입 금지에 반영
        armed[k] = False
    last_dates = {k: v.index[-1] for k, v in hist.items()}
    newest = max(last_dates.values())
    rows = []
    for fn in files:
        a, b = fn.split('_')
        if a not in hist:
            continue
        h = hist[a].copy()
        n_confirmed = len(h)
        stale = np.busday_count(last_dates[a].date(), newest.date()) >= 2
        P_ = pair_params.get(a, prm)
        if live and not stale:
            c, p = live.get(a, (None, None)) if isinstance(live, dict) else (naver_now(a), naver_now(b))
            if c and p:
                h.loc[pd.Timestamp(today)] = [c, p]      # 오늘 행이 이미 있으면 현재가로 덮어씀
                h = h.sort_index()
        d = indicators(h, P_).iloc[-1]
        ar = update_armed(armed.get(a, True), d.z, P_)   # 장중 값은 저장하지 않음(이번 계산에만 사용)
        row = dict(code=a, pref=b, date=str(h.index[-1].date()), C=d.C, P=d.P, dr=round(d.dr, 4),
                   z=round(d.z, 2), edge=round(d.edge, 4), rank=d['rank'], armed=ar,
                   validated=n_confirmed >= UNVALIDATED_MIN_ROWS, stale=bool(stale), model_holds=a in model['open'])
        if a in held:
            ps = held[a]
            days = int((h.index > pd.Timestamp(ps['entry_date'])).sum())     # 진입일 다음날부터 가격일까지 거래일 수
            pnl = pair_pnl(ps['c0'], ps['p0'], d.C, d.P, days, P_)
            why = exit_reason(d.z if np.isfinite(d.z) else np.inf, pnl, days, P_)
            row.update(held=True, name=ps['name'], entry_date=ps['entry_date'], days=days, pnl=round(pnl, 4),
                       action=f'EXIT_{why}' if why else 'HOLD')
        else:
            ok = entry_ok(d.z, d.edge, ar, P_) and row['validated'] and not stale
            row.update(held=False, action='ENTER_CANDIDATE' if ok else ('WATCH' if d.z >= P_.z_in else ''))
        rows.append(row)

    df = pd.DataFrame(rows)
    # 2) 시장 전체 필터(backtest와 동일): 거래 가능한 쌍 중 Z>=z_in 비율
    lv = df[df.validated & ~df.stale & np.isfinite(df.z)]
    zin = lv.code.map(lambda c: pair_params.get(c, prm).z_in)
    breadth = float((lv.z >= zin).mean()) if len(lv) else 0.0
    banned = in_blackout(today, blackout)
    if breadth > prm.max_breadth or banned:
        df.loc[df.action == 'ENTER_CANDIDATE', 'action'] = 'BLOCKED_BAN' if banned else 'WATCH'
    # 3) 슬롯 배정: 보유 수를 뺀 빈 칸만큼 rank(기본 edge) 순으로 ENTER
    n_held = int(df.held.sum())
    n_exit = int(df.action.str.startswith('EXIT').sum())
    free = max(slots - (n_held - n_exit), 0)
    cand = df[df.action == 'ENTER_CANDIDATE'].sort_values('rank', ascending=False)
    df.loc[cand.index[:free], 'action'] = 'ENTER'
    df.loc[df.action == 'ENTER_CANDIDATE', 'action'] = 'WAIT_SLOT'
    if capital:
        unit = capital / slots
        m = df.action == 'ENTER'
        df.loc[m, 'qty_C'] = (unit / df.loc[m, 'C']).round(-1)
        df.loc[m, 'qty_P'] = (unit / df.loc[m, 'P']).round(-1)
    upd = datetime.now().isoformat(timespec='seconds')
    out = dict(updated=upd, params=prm.to_dict(), slots=slots, free_slots=free, breadth=breadth, short_ban=banned,
               model_open=model['open'], actual_open=sorted(held),
               signals=json.loads(df.drop(columns=['rank']).to_json(orient='records', force_ascii=False)))
    tmp = OUT + '.tmp'
    json.dump(out, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(tmp, OUT)
    # 신호 기록(실제 체결가와 비교해 슬리피지를 측정하기 위함)
    act = df[df.action.isin(['ENTER']) | df.action.str.startswith('EXIT')]
    if len(act):
        logf = LOG
        act.assign(ts=upd)[['ts', 'code', 'pref', 'action', 'C', 'P', 'z']].to_csv(
            logf, mode='a', header=not os.path.exists(logf), index=False)
    return df, model


def format_msg(df: pd.DataFrame, prm: Params) -> str:
    lines = [f'📊 stmon v2 {datetime.now():%m-%d %H:%M}  (Z진입 {prm.z_in} / 청산 {prm.z_out} / 손절 {prm.stop:.0%})']
    for _, r in df[df.action.str.startswith('EXIT')].iterrows():
        lines.append(f"🔴 {r.action} {r.get('name', r.code)}  Z {r.z:+.2f}  손익 {r.pnl:+.1%}  {int(r.days)}일")
    for _, r in df[df.action == 'ENTER'].iterrows():
        q = f"  보S {int(r.qty_C)}주/우L {int(r.qty_P)}주" if 'qty_C' in r and not pd.isna(r.get('qty_C')) else ''
        lines.append(f"🟢 ENTER {r.code}/{r.pref}  Z {r.z:+.2f}  기대 {r.edge:.1%}{q}")
    if (df.action == 'BLOCKED_BAN').any():
        lines.append('⛔ 공매도 금지 기간: 신규 진입 없음 (' + ', '.join(df.loc[df.action == 'BLOCKED_BAN', 'code']) + ')')
    w = df[df.action == 'WAIT_SLOT']
    if len(w):
        lines.append('⏳ 슬롯 부족 대기: ' + ', '.join(w.code))
    for _, r in df[df.action == 'HOLD'].iterrows():
        lines.append(f"⚪ HOLD {r.get('name', r.code)}  Z {r.z:+.2f}  손익 {r.pnl:+.1%}")
    if len(lines) == 1:
        lines.append('신호 없음')
    return '\n'.join(lines)


def run_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument('--update', action='store_true', help='네이버 일봉으로 data/history 갱신 후 계산')
    ap.add_argument('--no-live', action='store_true', help='현재가 대신 마지막 확정 종가로 계산')
    a = ap.parse_args()
    import config
    prm = getattr(config, 'V2_PARAMS', Params())
    if a.update:
        for code, m in update_all_history():
            if m != 'ok':
                print('history', code, m)
    df, model = compute(prm, live=not a.no_live, slots=getattr(config, 'V2_SLOTS', 10),
                        capital=getattr(config, 'V2_CAPITAL', None), pair_params=getattr(config, 'V2_PAIR_PARAMS', {}),
                        blackout=getattr(config, 'V2_BLACKOUT', None))
    held = set(df.loc[df.held, 'code'])
    if set(model['open']) != held:
        print(f"참고: 모델 보유 {sorted(model['open'])} / 실제 보유 {sorted(held)}")
    cols = [c for c in ['code', 'name', 'z', 'edge', 'pnl', 'days', 'action'] if c in df]
    print(df[df.action != ''][cols].to_string(index=False))
    print('\n' + format_msg(df, prm))


if __name__ == '__main__':
    run_cli()
