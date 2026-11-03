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
LISTING = os.path.join(ROOT, 'data', 'listing.json')
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


def _source() -> str:
    """config.V2_DATA_SOURCE: 'kis'(KRX 기준, 실패 시 네이버) 또는 'naver'"""
    try:
        import config
        return getattr(config, 'V2_DATA_SOURCE', 'naver')
    except Exception:
        return 'naver'


def daily(code: str, count: int = 40) -> pd.DataFrame:
    """일봉(수정주가) close, volume — 설정이 kis면 KIS(KRX 종가) 먼저, 실패하면 네이버"""
    if _source() == 'kis':
        try:
            from core import kis
            df = kis.daily(code, count)
            if len(df):
                return df
        except Exception as e:
            log.warning(f'KIS 일봉 실패 {code}: {e} → 네이버')
    return naver_daily(code, count)


def update_pair(a: str, b: str, today: date, count: int = 40) -> tuple[str, dict]:
    """이력 CSV에 최근 일봉 추가. 겹치는 날 가격이 다르면(분할·감자 등 수정주가 재계산) 과거 전체를 비율 조정.
    장 마감 확정(15:40) 전에는 오늘 봉을 저장하지 않음. 반환: (결과, 거래대금 정보)"""
    f = os.path.join(HIST, f'{a}_{b}.csv')
    h = pd.read_csv(f, index_col=0, parse_dates=True)
    da, db = daily(a, count), daily(b, count)
    new = pd.DataFrame({'C': da.close, 'P': db.close}).dropna()
    if len(new) and len(new.index.intersection(h.index)) == 0:
        da, db = daily(a, 600), daily(b, 600)
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
        # 이어붙이는 경계(가장 오래된 겹친 날들)에서 비율 측정. 분할·감자 등 수정주가 재계산이면
        # 이 날들이 모두 같은 비율로 달라짐. 최근 하루 종가 차이(NXT 등)는 아래에서 네이버 값으로 덮어씀.
        head = ov[:5]
        r = new.loc[head] / h.loc[head]
        k = r.median()
        if (abs(k - 1) > 0.002).any():
            if ((r - k).abs() <= 0.003).all().all():
                h = h * k
                msg = f'rescaled C×{k.C:.4f} P×{k.P:.4f}'
            else:
                msg = f'check C×{k.C:.4f} P×{k.P:.4f} (경계 비율 불안정, 재조정 안 함)'
    h = pd.concat([h[h.index < new.index[0]], new]).sort_index()
    h = h[~h.index.duplicated(keep='last')]
    tmp = f + '.tmp'
    h.round(4).to_csv(tmp)
    os.replace(tmp, f)
    return msg, liq


def stale_pairs(pairs=None, lag_days: int = 3) -> dict[str, str]:
    """마지막 거래일이 전체 최신 거래일보다 lag_days 영업일 이상 뒤처진 쌍 {보통주코드: 마지막 거래일}"""
    import numpy as np
    last = {}
    for a, b in (pairs or pair_files()):
        try:
            last[a] = load_pair(a, b).index[-1]
        except Exception:
            continue
    if not last:
        return {}
    newest = max(last.values())
    return {a: str(d.date()) for a, d in last.items() if np.busday_count(d.date(), newest.date()) >= lag_days}


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
    st = stale_pairs(pairs)
    out = [(a, f'stale {st[a]}' if a in st and m in ('ok', 'no data') else m) for a, m in out]
    return out


def liquidity() -> dict:
    """{보통주코드: {'C': 거래대금, 'P': 거래대금, 'block': 차단 사유, 'warn': 주의 사유}}"""
    try:
        liq = json.load(open(LIQ, encoding='utf-8')).get('avg20_value', {})
    except Exception:
        liq = {}
    try:
        for a, v in json.load(open(LISTING, encoding='utf-8')).get('pairs', {}).items():
            liq.setdefault(a, {}).update(block=v.get('block', ''), warn=v.get('warn', ''))
    except Exception:
        pass
    return liq


# ---------------------------------------------------------------- 상장 유지 위험
PREF_CAP_MIN, PREF_CAP_WARN, PREF_SHARES_MIN, COMMON_CAP_WARN = 20, 30, 50_000, 500   # 억원, 주
WARN_NAME = {'01': '투자주의', '02': '투자경고', '03': '투자위험'}


def listing_flags(c: dict | None, p: dict | None) -> tuple[str, str]:
    block, warn = [], []
    for side, x in (('보통주', c), ('우선주', p)):
        if not x:
            continue
        if x['sltr']:
            block.append(f'{side} 정리매매')
        if x['mang']:
            block.append(f'{side} 관리종목')
        if x['stop']:
            block.append(f'{side} 거래정지')
        if not x['price'] and not (x['sltr'] or x['stop']):
            block.append(f'{side} 가격 없음')
        if x['warn'] not in ('00', '', '0'):
            warn.append(f"{side} {WARN_NAME.get(x['warn'], '시장경보 ' + x['warn'])}")
    if p and p['price']:
        if p['cap'] < PREF_CAP_MIN:
            block.append(f"우선주 시총 {p['cap']:.0f}억 < {PREF_CAP_MIN}억")
        elif p['cap'] < PREF_CAP_WARN:
            warn.append(f"우선주 시총 {p['cap']:.0f}억 (기준 {PREF_CAP_MIN}억 근접)")
        if 0 < p['shares'] < PREF_SHARES_MIN:
            warn.append(f"우선주 상장주식 {p['shares']:,}주 < 5만주")
    if c and c['price'] and c['cap'] < COMMON_CAP_WARN:
        warn.append(f"보통주 시총 {c['cap']:.0f}억 (2027년 기준 {COMMON_CAP_WARN}억 미만)")
    return '; '.join(block), '; '.join(warn)


def update_listing(pairs=None) -> list[tuple[str, str, bool]]:
    """KIS 종목 상태로 data/listing.json 갱신. 반환: 새로 걸리거나 사유가 바뀐 쌍 [(코드, 사유, 차단여부)]"""
    from core import kis
    try:
        prev = json.load(open(LISTING, encoding='utf-8')).get('pairs', {})
    except Exception:
        prev = {}
    out = {}
    for a, b in (pairs or pair_files()):
        try:
            c, p = kis.status(a), kis.status(b)
        except Exception as e:
            log.warning(f'종목 상태 조회 실패 {a}/{b}: {e}')
            continue
        blk, wrn = listing_flags(c, p)
        out[a] = dict(pref=b, C=c, P=p, block=blk, warn=wrn)
    if out:
        write_json({'updated': datetime.now().isoformat(timespec='seconds'), 'pairs': out}, LISTING)
    return [(a, v['block'] or v['warn'], bool(v['block'])) for a, v in out.items()
            if (v['block'] or v['warn']) and (v['block'], v['warn']) != (prev.get(a, {}).get('block', ''), prev.get(a, {}).get('warn', ''))]


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
    """현재가 {코드: 가격}. 설정이 kis면 KIS(KRX) 먼저, 빠진 종목은 네이버로."""
    codes = list(dict.fromkeys(codes))
    out: dict[str, float] = {}
    if _source() == 'kis':
        try:
            from core import kis
            out.update(kis.prices(codes))
        except Exception as e:
            log.warning(f'KIS 현재가 실패: {e} → 네이버')
    miss = [c for c in codes if c not in out]
    if miss:
        out.update(_fetch_now_naver(miss, chunk))
    return out


def _fetch_now_naver(codes: list[str], chunk: int = 40) -> dict[str, float]:
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
