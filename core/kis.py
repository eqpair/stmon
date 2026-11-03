"""
KIS(한국투자증권) 시세 — KRX 기준(시장코드 J)
- 앱키·토큰은 semon과 공유: ~/semon/.env 의 키, ~/semon/.kis_token.json 토큰(같은 형식으로 읽고, 만료 시 발급해 같은 파일에 저장)
- 초당 호출 한도를 semon과 나눠 쓰므로 호출 간격 GAP(기본 0.17초 ≈ 초당 6건) + 한도 초과(EGW00201) 시 재시도
- 실패하면 예외 → 호출하는 쪽(core/data.py)이 네이버로 대신 받음
"""
from __future__ import annotations
import json, os, re, time, threading, logging, urllib.request, urllib.parse, urllib.error
from datetime import date, timedelta
import pandas as pd

log = logging.getLogger(__name__)
SEMON = os.path.expanduser(os.environ.get('SEMON_DIR', '~/semon'))
BASE = 'https://openapi.koreainvestment.com:9443'
TOKEN_PATH = os.path.join(SEMON, '.kis_token.json')
TTL = 86400 - 300
GAP = 0.17
PRICE = '/uapi/domestic-stock/v1/quotations/inquire-price'
DAILY = '/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice'
ASK = '/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn'

_lock = threading.Lock()
_tok_lock = threading.Lock()
_last = [0.0]
_keys: dict = {}


def _read_env() -> dict:
    env = {}
    p = os.path.join(SEMON, '.env')
    if os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            if k.startswith('export '):
                k = k[7:].strip()
            env[k] = v.strip().strip('"').strip("'")
    return env


def keys() -> tuple[str, str]:
    """semon kis_auth.py가 읽는 환경변수 이름을 찾아 .env에서 값을 가져옴"""
    if _keys:
        return _keys['k'], _keys['s']
    src = open(os.path.join(SEMON, 'kis_auth.py'), encoding='utf-8').read()

    def name(var):
        for pat in (rf'^{var}\s*=\s*os\.(?:getenv|environ\.get)\(\s*["\'](\w+)["\']',
                    rf'^{var}\s*=\s*os\.environ\[\s*["\'](\w+)["\']\s*\]'):
            m = re.search(pat, src, re.M)
            if m:
                return m.group(1)
        raise RuntimeError(f'semon/kis_auth.py에서 {var} 환경변수 이름을 찾지 못함')
    env = {**_read_env(), **os.environ}
    _keys['k'], _keys['s'] = env[name('APP_KEY')], env[name('APP_SECRET')]
    return _keys['k'], _keys['s']


def token(force: bool = False) -> str:
    with _tok_lock:
        if not force:
            try:
                d = json.load(open(TOKEN_PATH))
                if time.time() - d['issued_at'] < TTL:
                    return d['token']
            except Exception:
                pass
        k, s = keys()
        body = json.dumps({'grant_type': 'client_credentials', 'appkey': k, 'appsecret': s}).encode()
        req = urllib.request.Request(BASE + '/oauth2/tokenP', data=body, headers={'content-type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as r:
            t = json.loads(r.read())['access_token']
        tmp = TOKEN_PATH + '.stmon.tmp'
        with open(tmp, 'w') as f:
            json.dump({'token': t, 'issued_at': time.time()}, f)
        os.replace(tmp, TOKEN_PATH)
        log.info('KIS 토큰 발급(semon과 공유 파일에 저장)')
        return t


def _call(path: str, tr: str, params: dict, tries: int = 4) -> dict:
    k, s = keys()
    url = BASE + path + '?' + urllib.parse.urlencode(params)
    refreshed = False
    for _ in range(tries):
        with _lock:
            w = _last[0] + GAP - time.time()
            if w > 0:
                time.sleep(w)
            _last[0] = time.time()
        req = urllib.request.Request(url, headers={
            'authorization': f'Bearer {token()}', 'appkey': k, 'appsecret': s, 'tr_id': tr,
            'custtype': 'P', 'content-type': 'application/json; charset=utf-8'})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read().decode('utf-8', 'ignore'))
        except urllib.error.HTTPError as e:
            try:
                d = json.loads(e.read().decode('utf-8', 'ignore'))
            except Exception:
                d = {'rt_cd': 'X', 'msg_cd': f'HTTP{e.code}', 'msg1': str(e)}
        if d.get('rt_cd') == '0':
            return d
        mc = str(d.get('msg_cd', ''))
        if mc == 'EGW00201':                         # 초당 한도 초과 → 잠시 후 재시도
            time.sleep(1.0)
            continue
        if mc in ('EGW00121', 'EGW00123') and not refreshed:   # 토큰 무효·만료
            token(force=True)
            refreshed = True
            continue
        raise RuntimeError(f"KIS {tr} {mc} {d.get('msg1', '')}".strip())
    raise RuntimeError(f'KIS {tr} 재시도 초과')


def price(code: str) -> float | None:
    """KRX 현재가(장 시작 전·마감 후는 최근 체결가)"""
    d = _call(PRICE, 'FHKST01010100', {'fid_cond_mrkt_div_code': 'J', 'fid_input_iscd': code})
    try:
        p = float((d.get('output') or {}).get('stck_prpr') or 0)
    except ValueError:
        p = 0
    return p if p > 0 else None


def prices(codes: list[str]) -> dict[str, float]:
    """여러 종목 현재가. 처음부터 5번 연속 실패하면(KIS 장애) 바로 중단 → 네이버로 대체"""
    out, fail = {}, 0
    for c in codes:
        try:
            p = price(c)
            if p:
                out[c] = p
            fail = 0
        except Exception as e:
            fail += 1
            log.debug(f'KIS 현재가 실패 {c}: {e}')
            if fail >= 5 and not out:
                raise RuntimeError(f'KIS 연속 실패: {e}')
    return out


def daily(code: str, count: int = 40) -> pd.DataFrame:
    """KRX 수정주가 일봉(최근 count거래일): columns close, volume. 한 번에 최대 100일씩 거슬러 올라감"""
    rows: dict = {}
    end = date.today()
    for _ in range(max(1, count // 90 + 2)):
        start = end - timedelta(days=140)
        d = _call(DAILY, 'FHKST03010100', {
            'fid_cond_mrkt_div_code': 'J', 'fid_input_iscd': code,
            'fid_input_date_1': start.strftime('%Y%m%d'), 'fid_input_date_2': end.strftime('%Y%m%d'),
            'fid_period_div_code': 'D', 'fid_org_adj_prc': '0'})
        got = 0
        for r in d.get('output2') or []:
            dt = r.get('stck_bsop_date')
            try:
                c = float(r.get('stck_clpr') or 0)
                v = float(r.get('acml_vol') or 0)
            except ValueError:
                continue
            if dt and c > 0:
                rows[pd.Timestamp(dt)] = (c, v)
                got += 1
        if not got or len(rows) >= count:
            break
        end = start - timedelta(days=1)
    df = pd.DataFrame.from_dict(rows, orient='index', columns=['close', 'volume']).sort_index()
    return df.tail(count)


def asking(code: str) -> tuple[float | None, float | None]:
    """최우선 매도호가·매수호가(KRX)"""
    d = _call(ASK, 'FHKST01010200', {'fid_cond_mrkt_div_code': 'J', 'fid_input_iscd': code})
    o = d.get('output1') or {}
    try:
        a, b = float(o.get('askp1') or 0), float(o.get('bidp1') or 0)
    except ValueError:
        return None, None
    return (a or None), (b or None)


def status(code: str) -> dict:
    """종목 상태: 가격, 시가총액(억원), 상장주식수, 관리종목·정리매매·거래정지·시장경보"""
    o = _call(PRICE, 'FHKST01010100', {'fid_cond_mrkt_div_code': 'J', 'fid_input_iscd': code}).get('output') or {}

    def num(k):
        try:
            return float(o.get(k) or 0)
        except ValueError:
            return 0.0
    st = str(o.get('iscd_stat_cls_code') or '')
    return dict(price=num('stck_prpr'), cap=num('hts_avls'), shares=int(num('lstn_stcn')), stat=st,
                mang=o.get('mang_issu_cls_code') == 'Y' or st == '51', sltr=o.get('sltr_yn') == 'Y',
                stop=o.get('temp_stop_yn') == 'Y' or st == '58', warn=str(o.get('mrkt_warn_cls_code') or '00'),
                caful=o.get('invt_caful_yn') == 'Y')
