"""
데이터 계층 — 일봉 이력(data/history), 현재가, 거래대금

- 이력: data/history/{보통주}_{우선주}.csv (date, C, P 수정주가). 1995년~ DataGuide + 네이버 일봉.
- 현재가: 네이버 실시간 API. 여러 종목을 한 번에 조회하고, 실패하면 종목별로 다시 조회.
- 거래대금: 15:45 이력 갱신 때 네이버 일봉의 거래량으로 20일 평균 거래대금을 계산해 data/liquidity.json 저장.
"""
from __future__ import annotations
import json, os, re, time, logging, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import pandas as pd

log = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, 'data', 'history')
LIQ = os.path.join(ROOT, 'data', 'liquidity.json')
UA = {'User-Agent': 'Mozilla/5.0'}


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')


def write_json(obj, path):
    """원자적 저장(NaN → null)"""
    def clean(v):
        if isinstance(v, float) and (v != v or v in (float('inf'), float('-inf'))):
            return None
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        if hasattr(v, 'item'):            # numpy scalar
            return clean(v.item())
        return v
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(clean(obj), f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------------------------------------------------------------- 이력
def pair_files() -> list[tuple[str, str]]:
    return sorted(tuple(f[:-4].split('_')) for f in os.listdir(HIST) if f.endswith('.csv'))


def load_pair(a: str, b: str) -> pd.DataFrame:
    h = pd.read_csv(os.path.join(HIST, f'{a}_{b}.csv'), index_col=0, parse_dates=True)
    return h[(h.C > 0) & (h.P > 0)].dropna()


def load_all(pairs: list[tuple[str, str]] | None = None, min_rows: int = 0) -> dict[str, pd.DataFrame]:
    out = {}
    for a, b in (pairs or pair_files()):
        try:
            h = load_pair(a, b)
        except FileNotFoundError:
            log.warning(f'이력 파일 없음: {a}_{b}.csv')
            continue
        if len(h) >= min_rows:
            out[a] = h
    return out


def naver_daily(code: str, count: int = 40) -> pd.DataFrame:
    """네이버 일봉(수정주가): columns close, volume"""
    txt = _get(f'https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0')
    rows = {}
    for r in re.findall(r'data="([^"]+)"', txt):
        f = r.split('|')
        if len(f) >= 6 and float(f[4]) > 0:
            rows[pd.Timestamp(f[0])] = (float(f[4]), float(f[5]))
    return pd.DataFrame.from_dict(rows, orient='index', columns=['close', 'volume']).sort_index()


def update_pair(a: str, b: str, today: date) -> tuple[str, dict]:
    """이력 CSV에 최근 일봉 추가. 겹치는 날 가격이 다르면(분할·감자 등 수정주가 재계산) 과거 전체를 비율 조정.
    장 마감 확정(15:40) 전에는 오늘 봉을 저장하지 않음. 반환: (결과, 거래대금 정보)"""
    f = os.path.join(HIST, f'{a}_{b}.csv')
    h = pd.read_csv(f, index_col=0, parse_dates=True)
    da, db = naver_daily(a), naver_daily(b)
    new = pd.DataFrame({'C': da.close, 'P': db.close}).dropna()
    if len(new) and len(new.index.intersection(h.index)) == 0:
        da, db = naver_daily(a, 600), naver_daily(b, 600)
        new = pd.DataFrame({'C': da.close, 'P': db.close}).dropna()
        if len(new.index.intersection(h.index)) == 0:
            raise RuntimeError('이력과 겹치는 날짜가 없어 이어붙일 수 없음')
    now = datetime.now()
    after_close = now.hour * 60 + now.minute >= 15 * 60 + 40
    new = new[(new.index.date < today) | (after_close & (new.index.date == today))]
    liq = {'C': float((da.close * da.volume).tail(20).mean()) if len(da) else None,
           'P': float((db.close * db.volume).tail(20).mean()) if len(db) else None}
    if new.empty:
        return 'no data', liq
    msg = 'ok'
    ov = new.index.intersection(h.index)
    if len(ov):
        last = ov[-1]
        k = new.loc[last] / h.loc[last]
        if (abs(k - 1) > 0.002).any():
            h = h * k
            msg = f'rescaled C×{k.C:.4f} P×{k.P:.4f}'
    h = pd.concat([h[h.index < new.index[0]], new]).sort_index()
    h = h[~h.index.duplicated(keep='last')]
    tmp = f + '.tmp'
    h.round(4).to_csv(tmp)
    os.replace(tmp, f)
    return msg, liq


def update_all(today: date | None = None, pairs=None) -> list[tuple[str, str]]:
    today = today or date.today()
    out, liq = [], {}
    for a, b in (pairs or pair_files()):
        try:
            m, l = update_pair(a, b, today)
            liq[a] = l
            out.append((a, m))
        except Exception as e:
            out.append((a, f'update fail {e}'))
        time.sleep(0.15)
    if liq:
        write_json({'updated': datetime.now().isoformat(timespec='seconds'), 'avg20_value': liq}, LIQ)
    return out


def liquidity() -> dict:
    try:
        return json.load(open(LIQ, encoding='utf-8')).get('avg20_value', {})
    except Exception:
        return {}


# ---------------------------------------------------------------- 현재가
def _parse_realtime(txt: str) -> dict[str, float]:
    j = json.loads(txt)
    out = {}
    for area in j.get('result', {}).get('areas', []):
        for d in area.get('datas', []):
            cd, nv = d.get('cd'), d.get('nv')
            try:
                if cd and nv is not None and float(nv) > 0:
                    out[str(cd)] = float(nv)
            except (TypeError, ValueError):
                pass
    return out


def fetch_now(codes: list[str], chunk: int = 40) -> dict[str, float]:
    """현재가 {코드: 가격}. 묶음 조회 후 빠진 종목만 개별 조회. 0원(거래 없음)은 제외."""
    codes = list(dict.fromkeys(codes))
    out: dict[str, float] = {}
    for i in range(0, len(codes), chunk):
        part = codes[i:i + chunk]
        try:
            out.update(_parse_realtime(_get('https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:'
                                            + ','.join(part), 8)))
        except Exception as e:
            log.warning(f'현재가 묶음 조회 실패({len(part)}종목): {e}')
    missing = [c for c in codes if c not in out]

    def one(c):
        try:
            return c, _parse_realtime(_get(f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{c}', 5)).get(c)
        except Exception:
            return c, None
    if missing:
        with ThreadPoolExecutor(8) as ex:
            for c, v in ex.map(one, missing):
                if v:
                    out[c] = v
    return out
