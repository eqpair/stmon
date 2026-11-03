"""
텔레그램 봇 (aiogram 3) — 알림 발송 + 명령

조회:  /p 보유  /w 관심(진입 근접)  /o 지금 기준 주문표(미리보기)  /r 성과 리포트  /h 도움말
기록:  /in  코드 보통주수량@가격 우선주수량@가격 [YYYY-MM-DD]
       /out 코드 보통주가격 우선주가격 [STOP|TARGET|TIME|MANUAL] [YYYY-MM-DD]
기록 명령은 config의 CHAT_ID 방 또는 ALLOWED_USER_IDS 사용자만 가능.
"""
from __future__ import annotations
import asyncio, logging, re
from datetime import date
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

log = logging.getLogger(__name__)


# 텔레그램 표시용: 종목명 앞 신호등 이모지와 '(비)' 제거 (주문표의 🔴청산/🟢진입/⚪보유 표시는 유지)
_NAME_EM = re.compile(r'[🔴🟠🟡🟢🔵🟣⚪⚫🟤]\uFE0F?[ \t]*(?=[^\s<])(?!보유)')


def clean_names(t: str) -> str:
    return _NAME_EM.sub('', t.replace('(비)', ''))


try:
    from aiogram.client.session.middlewares.base import BaseRequestMiddleware

    class _CleanNames(BaseRequestMiddleware):
        async def __call__(self, make_request, bot, method):
            if isinstance(getattr(method, 'text', None), str):
                method.text = clean_names(method.text)
            return await make_request(bot, method)
except Exception:          # 구버전 aiogram이면 생략
    _CleanNames = None


class TgBot:
    def __init__(self, app, token: str, chat_id: str, allowed_users=()):
        self.app = app
        self.chat_id = str(chat_id)
        self.allowed = {str(u) for u in allowed_users}
        self.bot = Bot(token=token)
        if _CleanNames:
            self.bot.session.middleware(_CleanNames())
        self.dp = Dispatcher()
        self._routes()

    def _ok(self, m: types.Message) -> bool:
        # 알림 채널(채널 게시물은 from_user 없음) 또는 허용된 사용자
        return str(m.chat.id) == self.chat_id or bool(m.from_user and str(m.from_user.id) in self.allowed)

    async def send(self, text: str):
        for i in range(0, len(text), 3900):
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=text[i:i + 3900], parse_mode='HTML')
            except Exception as e:
                log.error(f'텔레그램 전송 실패: {e}')
            await asyncio.sleep(0.3)

    def _routes(self):
        dp, app = self.dp, self.app

        def on(*cmds):
            """일반 대화(message)와 채널 게시물(channel_post) 모두에서 명령을 받음"""
            def deco(f):
                dp.message.register(f, Command(*cmds))
                dp.channel_post.register(f, Command(*cmds))
                return f
            return deco

        async def guard(m):
            if not self._ok(m):
                log.warning(f'허용되지 않은 사용자 명령 무시: chat={m.chat.id} user={getattr(m.from_user, "id", None)}')
                return False
            return True

        @on('h', 'help', 'start')
        async def h(m: types.Message):
            if await guard(m):
                await m.reply(__doc__.split('\n', 2)[2])

        @on('p', 'c')
        async def p(m: types.Message):
            if await guard(m):
                await m.reply(app.text_positions(), parse_mode='HTML')

        @on('w', 'd')
        async def w(m: types.Message):
            if await guard(m):
                await m.reply(app.text_watch(), parse_mode='HTML')

        @on('o', 'v2')
        async def o(m: types.Message):
            if await guard(m):
                txt = await app.preview_orders()
                await m.reply(txt, parse_mode='HTML')

        @on('r')
        async def r(m: types.Message):
            if await guard(m):
                await m.reply(app.text_report(), parse_mode='HTML')

        @on('in')
        async def cin(m: types.Message):
            if not await guard(m):
                return
            mt = re.match(r'/in(?:@\w+)?\s+(\d{6})\s+(\d+)@([\d.,]+)\s+(\d+)@([\d.,]+)(?:\s+(\d{4}-\d{2}-\d{2}))?\s*$', m.text or '')
            if not mt:
                await m.reply('형식: /in 005300 300@123400 470@98000 [2026-11-02]')
                return
            code, cq, cp, pq, pp, d = mt.groups()
            try:
                t = app.record_in(code, int(cq), float(cp.replace(',', '')), int(pq), float(pp.replace(',', '')),
                                  date.fromisoformat(d) if d else None)
                await m.reply(f"✅ 진입 기록 {t['pair_name']}\n보통주 숏 {t['common_qty']}주 @{t['common_entry']:,.0f} · "
                              f"우선주 롱 {t['preferred_qty']}주 @{t['preferred_entry']:,.0f}\n(id {t['trade_id']})")
            except Exception as e:
                await m.reply(f'기록 실패: {e}')

        @on('out')
        async def cout(m: types.Message):
            if not await guard(m):
                return
            mt = re.match(r'/out(?:@\w+)?\s+(\d{6})\s+([\d.,]+)\s+([\d.,]+)(?:\s+([A-Za-z]+))?(?:\s+(\d{4}-\d{2}-\d{2}))?\s*$', m.text or '')
            if not mt:
                await m.reply('형식: /out 005300 120500 99100 [STOP] [2026-11-02]')
                return
            code, cp, pp, why, d = mt.groups()
            try:
                res = app.record_out(code, float(cp.replace(',', '')), float(pp.replace(',', '')), why or '',
                                     date.fromisoformat(d) if d else None)
                await m.reply(res)
            except Exception as e:
                await m.reply(f'기록 실패: {e}')

    async def start(self):
        try:
            await self.bot.delete_webhook()
        except Exception:
            pass
        await self.dp.start_polling(self.bot, handle_signals=False)

    async def stop(self):
        try:
            await self.dp.stop_polling()
            await self.bot.session.close()
        except Exception:
            pass
