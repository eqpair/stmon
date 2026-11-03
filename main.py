#!/usr/bin/env python3
"""
stmon — 보통주 숏 / 우선주 롱 매매 프로그램 (주문은 직접, 나머지는 자동)

장중(평일 08:30~16:30) WAIT_TIME마다:
  현재가 일괄 조회 → 쌍별 Z·보유 손익 계산 → 웹 JSON 갱신 → 장중 알림(손절선 접근/도달, 진입 근접)
15:15  주문표(진입·청산·수량) 텔레그램 발송, 신호 기록
15:45  확정 종가로 이력 갱신 → 재진입 상태·백테스트 재생 → 일별 손익 기록 → 트렌드 JSON → (금) 주간 리포트
체결 기록: 텔레그램 /in, /out → data/pair-trades.json
"""
import os, sys, asyncio, atexit, logging, subprocess
from logging.handlers import RotatingFileHandler
from datetime import datetime, date, timedelta
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

os.makedirs('logs', exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[RotatingFileHandler('logs/stock_monitor.log', maxBytes=10 * 1024 * 1024, backupCount=5),
                              logging.StreamHandler()])
log = logging.getLogger('stmon')

import config as cfg
from core import data, decide, ledger, report, web, regime
from core.decide import Risk
from modules.utils import format_stock_name


def single_instance(path='/tmp/stmon_telegram.lock'):
    if os.path.exists(path):
        pid = open(path).read().strip()
        if pid and os.path.exists(f'/proc/{pid}'):
            print(f'이미 실행 중 (PID {pid})')
            sys.exit(1)
    open(path, 'w').write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(path) and os.remove(path))


class App:
    def __init__(self):
        self.prm = cfg.V2_PARAMS
        self.pp = cfg.V2_PAIR_PARAMS
        self.risk = Risk(capital=cfg.V2_CAPITAL, slots=cfg.V2_SLOTS, gross_limit=cfg.V2_GROSS_LIMIT,
                         liq_frac=cfg.V2_LIQ_FRAC, stop_warn=cfg.V2_STOP_WARN, bench_rate=cfg.V2_BENCH_RATE,
                         sp_short=cfg.V2_SPREAD_SHORT, sp_long=cfg.V2_SPREAD_LONG,
                         leg_min=getattr(cfg, 'V2_STOCK_MIN', None), leg_max=getattr(cfg, 'V2_STOCK_MAX', None),
                         adv_mult=getattr(cfg, 'V2_ADV_MULT', 1.5), day_frac=getattr(cfg, 'V2_DAY_FRAC', 0.3))
        have = set(data.pair_files())
        self.pairs = [(a, b) for a, b, *_ in cfg.TICK_PAIRS if (a, b) in have]
        miss = [(a, b) for a, b, *_ in cfg.TICK_PAIRS if (a, b) not in have]
        if miss:
            log.warning(f'이력 파일이 없어 제외: {miss}')
        self.names = {a: format_stock_name(a) for a, _ in self.pairs}
        self.prefs = {a: b for a, b in self.pairs}
        self.hist, self.model, self.model_r, self.liq = {}, {'armed': {}, 'open': []}, None, {}
        self.armed = {}
        self.snap = None
        self.last_orders = None
        self.live_px = {}                # 이번 주기 현재가(시장 변동성 계산용)
        self.live_orders = None          # 매 주기 현재가 기준 판단(웹 표시용, 기록 안 함)
        self.done = {}                  # 하루 1회 작업 기록: {작업: 날짜}
        self.alerted = {}               # 장중 알림 중복 방지: {(코드, 종류): 날짜}
        self.tg = None
        if cfg.TELEGRAM_TOKEN:
            from bot import TgBot
            self.tg = TgBot(self, cfg.TELEGRAM_TOKEN, cfg.CHAT_ID, cfg.ALLOWED_USER_IDS)
        else:
            log.error('텔레그램 토큰 없음(config_secrets.py) — 알림 없이 실행')

    # ------------------------------------------------------------ 상태 준비
    def params_for(self, a):
        return self.pp.get(a, self.prm)

    def reload(self):
        self.hist = data.load_all(self.pairs, min_rows=self.prm.min_history + 2)
        self.model, self.model_r = decide.model_state(self.hist, self.prm, self.risk.slots, cfg.V2_BLACKOUT, self.pp,
                                                            entry_block=self.vol_block_series())
        trades = ledger.load()
        self.armed = dict(self.model['armed'])
        for a in decide.actual_stop_blocks(self.hist, self.prm, trades):
            self.armed[a] = False
        self.liq = data.liquidity()
        log.info(f"이력 {len(self.hist)}쌍 로드, 모델 보유 {self.model['open']}, "
                 f"재진입 대기 {sorted(k for k, v in self.armed.items() if not v)}")

    def vol_block_series(self):
        th = getattr(cfg, 'V2_VOL_BLOCK', None)
        return (regime.vol_ratio_series(self.hist) > th) if th else None

    def vol_args(self):
        try:
            v = regime.vol_ratio_now(self.hist, self.live_px)
        except Exception as e:
            log.error(f'시장 변동성 계산 실패: {e}'); v = None
        return dict(vol_ratio=v, vol_block=getattr(cfg, 'V2_VOL_BLOCK', None))

    def compute_snapshot(self, live: dict):
        self.snap = decide.snapshot(self.hist, live, self.pairs, self.names, self.prm, self.pp, self.armed,
                                    ledger.open_positions())
        return self.snap

    def backtest_curve(self):
        if self.model_r is None:
            return {}
        r = self.model_r['2024-01-01':]
        eq = (1 + r).cumprod()
        m = eq.resample('W').last()
        return dict(dates=m.index.strftime('%Y-%m-%d').tolist(), equity=[round(float(x), 4) for x in m])

    # ------------------------------------------------------------ 텍스트
    def text_positions(self):
        s = self.snap
        if s is None or not s.held.any():
            return '보유 없음'
        L = ['<b>보유</b>']
        for r in s[s.held].itertuples():
            L.append(f"{r.name}\n  {int(r.cq)}/{int(r.pq)}주 · {int(r.days)}일 · Z {r.z:+.2f} · {r.pnl_won / 1e4:+,.0f}만원 "
                     f"({r.pnl_ret:+.1%}) · 손절까지 {r.stop_gap:.1%}" + (f" · <b>{r.exit}</b>" if isinstance(r.exit, str) else ''))
        tot = s.loc[s.held, 'pnl_won'].sum()
        L.append(f"합계 {tot / 1e4:+,.0f}만원")
        return '\n'.join(L)

    def text_watch(self):
        s = self.snap
        if s is None:
            return '데이터 준비 중'
        w = s[(~s.held) & (s.z >= s.z_in - 0.5)].sort_values('z', ascending=False).head(15)
        if not len(w):
            return '진입 근접 없음'
        return '<b>관심(Z 상위)</b>\n' + '\n'.join(
            f"{r.name}  Z {r.z:+.2f} · 기대 " + (f"{r.edge:.1%}" if r.edge == r.edge else "- (진입 제외)") + ('' if r.armed else ' · 재진입대기')
            + ('' if r.validated else ' · 이력부족') for r in w.itertuples())

    def text_report(self):
        return report.summary(self.risk.capital)

    # ------------------------------------------------------------ 체결 기록
    def record_in(self, code, cq, cp, pq, pp, when=None):
        if code not in self.prefs:
            raise ValueError(f'대상 쌍이 아님: {code}')
        t = ledger.record_entry(code, self.prefs[code], self.names[code], cq, cp, pq, pp,
                                self.risk.bench_rate, self.risk.sp_short, self.risk.sp_long, when)
        self.refresh_after_fill()
        return t

    def record_out(self, code, cp, pp, why='', when=None):
        pos = ledger.open_positions().get(code)
        if not pos:
            raise ValueError(f'보유 중이 아님: {code}')
        r = pos.pnl(cp, pp, when or date.today())
        closed = ledger.record_exit(code, cp, pp, why, when)
        if (why or '').upper() == 'STOP' or r['ret_strategy'] <= -self.prm.stop:
            self.armed[code] = False
        self.refresh_after_fill()
        return (f"✅ 청산 기록 {pos.name} ({len(closed)}건)\n손익 {r['total'] / 1e4:+,.0f}만원 ({r['ret']:+.1%}) · "
                f"{r['days']}일 · 금리 {r['financing'] / 1e4:+,.0f}만원")

    def refresh_after_fill(self):
        if self.snap is not None:
            live = {r.code: r.C for r in self.snap.itertuples() if r.live}
            live.update({r.pref: r.P for r in self.snap.itertuples() if r.live})
            self.compute_snapshot(live)
            self.write_web()

    # ------------------------------------------------------------ 작업
    async def fetch_live(self):
        codes = [c for a, b in self.pairs for c in (a, b)]
        return await asyncio.to_thread(data.fetch_now, codes)

    def write_web(self):
        try:
            self.live_orders = decide.orders(self.snap, self.prm, self.risk, cfg.V2_BLACKOUT, self.liq, **self.vol_args())
        except Exception as e:
            log.error(f'실시간 판단 계산 실패: {e}')
        web.stock_data(self.snap, self.hist)
        web.dashboard(self.snap, self.last_orders, self.model, self.prm, self.risk, self.backtest_curve(),
                      live_orders=self.live_orders, market_open=self.market_open())

    async def preview_orders(self, live=None):
        if live is None:
            live = await self.fetch_live()
        self.live_px = live
        snap = self.compute_snapshot(live)
        o = decide.orders(snap, self.prm, self.risk, cfg.V2_BLACKOUT, self.liq, **self.vol_args())
        return decide.fmt_orders(o, self.prm, self.model['open'])

    async def job_orders(self, live):
        o = decide.orders(self.snap, self.prm, self.risk, cfg.V2_BLACKOUT, self.liq, **self.vol_args())
        o.attrs['time'] = datetime.now().isoformat(timespec='seconds')
        self.last_orders = o
        report.log_signals(o)
        if getattr(cfg, 'TG_ORDER_SHEET', True):
            await self.send(decide.fmt_orders(o, self.prm, self.model['open']))
        log.info(f"주문표 발송: {o.action.value_counts().to_dict()}")

    async def job_close(self):
        res = await asyncio.to_thread(data.update_all, date.today(), self.pairs)
        stale = [f"{self.names.get(c, c)} ({c}) · 마지막 거래 {m.split()[1]}" for c, m in res if m.startswith('stale')]
        bad = [f'{c}:{m}' for c, m in res if m != 'ok' and not m.startswith('stale')]
        await asyncio.to_thread(self.reload)
        snap = self.compute_snapshot({})                 # 확정 종가 기준
        row = report.mark_equity(snap)
        await asyncio.to_thread(web.trends, self.hist, self.names, self.params_for)
        log.info(f"마감 처리: 이력 {len(res)}쌍(확인 필요 {len(bad)}), 손익 {row['total']:,.0f}")
        if getattr(cfg, 'TG_DAILY_WARNINGS', True):
            if bad:
                await self.send('⚠️ 이력 갱신 확인 필요\n' + '\n'.join(bad[:20]))
            if stale:
                await self.send('⛔ 거래 없음 — 상장폐지·거래정지 의심 (진입 후보에서는 자동 제외)\n' + '\n'.join(stale)
                                + '\n쌍 목록(config.py TICK_PAIRS)에서 빼는 걸 검토하세요.')
            if date.today().weekday() == 4:
                await self.send(self.text_report())

    async def intraday_alerts(self):
        if not getattr(cfg, 'TG_INTRADAY_ALERTS', False):
            return
        s, today = self.snap, date.today()
        for r in s[s.held].itertuples():
            if r.ret_rule <= -self.prm.stop:
                kind, msg = 'stop', f"🚨 손절선 도달(장중) {r.name}  손익 {r.ret_rule:+.1%} — 종가 기준으로 15:15 주문표에서 확정"
            elif r.ret_rule <= -self.risk.stop_warn:
                kind, msg = 'warn', f"⚠️ 손절선 접근 {r.name}  손익 {r.ret_rule:+.1%} (손절 -{self.prm.stop:.0%})"
            else:
                continue
            if self.alerted.get((r.code, kind)) != today and self.alerted.get((r.code, 'stop')) != today:
                self.alerted[(r.code, kind)] = today
                await self.send(msg)
        for r in s[(~s.held) & s.armed & s.validated & ~s.stale & (s.z >= s.z_in) & (s.edge >= self.prm.min_edge)].itertuples():
            if self.alerted.get((r.code, 'near')) != today:
                self.alerted[(r.code, 'near')] = today
                await self.send(f"👀 진입 조건 근접(장중) {r.name}  Z {r.z:+.2f} · 기대 {r.edge:.1%} — 확정은 15:15")

    async def send(self, text):
        if self.tg:
            await self.tg.send(text)
        else:
            log.info('[TG] ' + text.replace('\n', ' | '))

    def git_push(self):
        if not cfg.GIT_PUSH:
            return
        try:
            if not subprocess.run('git status --porcelain data', shell=True, capture_output=True, text=True).stdout.strip():
                return
            subprocess.run('git add data', shell=True, check=True)
            subprocess.run(f'git commit -q -m "데이터 업데이트: {datetime.now():%Y-%m-%d %H:%M:%S}"', shell=True, check=True)
            subprocess.run('git pull -q --rebase --autostash', shell=True, check=False)
            subprocess.run('git push -q', shell=True, check=True)
        except Exception as e:
            log.error(f'git push 실패: {e}')

    def due(self, name, hm):
        now = datetime.now()
        return now.weekday() < 5 and (now.hour, now.minute) >= tuple(hm) and self.done.get(name) != now.date()

    def market_open(self):
        now = datetime.now()
        (h1, m1), (h2, m2) = cfg.MARKET_HOURS
        return now.weekday() < 5 and (h1, m1) <= (now.hour, now.minute) <= (h2, m2)

    def restore_today(self):
        """재시작해도 오늘 이미 한 작업(주문표·마감)은 다시 하지 않음. 오늘 주문표는 대시보드에서 복원."""
        today = date.today().isoformat()
        try:
            import json
            d = json.load(open(os.path.join(ROOT, 'data', 'v2_dashboard.json'), encoding='utf-8'))
            if (d.get('orders_time') or '').startswith(today):
                self.done['orders'] = date.today()
                o = pd.DataFrame(d.get('orders') or [])
                if len(o):
                    o.attrs['time'] = d['orders_time']
                    self.last_orders = o
        except Exception:
            pass
        if os.path.exists(report.EQUITY):
            e = pd.read_csv(report.EQUITY)
            if len(e) and str(e.date.iloc[-1]) == today:
                self.done['close'] = date.today()
        log.info(f'오늘 완료된 작업: {list(self.done)}')

    async def loop(self):
        self.restore_today()
        await asyncio.to_thread(self.reload)
        await asyncio.to_thread(web.trends, self.hist, self.names, self.params_for)
        self.compute_snapshot({})
        self.write_web()
        while True:
            try:
                if not self.market_open():
                    await asyncio.sleep(60)
                    continue
                live = await self.fetch_live()
                self.live_px = live
                if len(live) < len(self.pairs):          # 장 시작 전·종목 정지 등은 확정 종가 사용
                    log.info(f'현재가 {len(live)}/{len(self.pairs) * 2}종목')
                snap = self.compute_snapshot(live)
                self.write_web()
                log.info(f"주기: 현재가 {len(live)}/{len(self.pairs) * 2}종목 · 보유 {int(snap.held.sum())} · "
                         f"Z≥진입 {int(((snap.z >= snap.z_in) & ~snap.held).sum())}쌍")
                await self.intraday_alerts()
                if self.due('orders', cfg.V2_SIGNAL_TIME) and datetime.now().time() < datetime.strptime(
                        '%02d:%02d' % tuple(cfg.V2_HISTORY_TIME), '%H:%M').time():
                    self.done['orders'] = date.today()
                    await self.job_orders(live)
                    self.write_web()
                if self.due('close', cfg.V2_HISTORY_TIME):
                    self.done['close'] = date.today()
                    await self.job_close()
                    self.write_web()
                await asyncio.to_thread(self.git_push)
                await asyncio.sleep(cfg.WAIT_TIME)
            except Exception as e:
                log.exception(f'주기 처리 오류: {e}')
                await asyncio.sleep(30)

    async def run(self):
        log.info('stmon 시작')
        tasks = [asyncio.create_task(self.loop())]
        if self.tg:
            tasks.append(asyncio.create_task(self.tg.start()))
        await asyncio.gather(*tasks)


if __name__ == '__main__':
    single_instance()
    try:
        asyncio.run(App().run())
    except KeyboardInterrupt:
        pass
