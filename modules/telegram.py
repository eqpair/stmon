from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
import logging
import asyncio
from config import TELEGRAM_TOKEN, CHAT_ID
from modules.utils import format_stock_name

logger = logging.getLogger(__name__)

class TelegramBot:
    _instance = None
    _initialized = False

    def __new__(cls, monitor):
        if cls._instance is None:
            cls._instance = super(TelegramBot, cls).__new__(cls)
        return cls._instance

    def __init__(self, monitor):
        if not TelegramBot._initialized:
            self.bot = Bot(token=TELEGRAM_TOKEN)
            self.storage = MemoryStorage()
            self.dp = Dispatcher(storage=self.storage)
            self.monitor = monitor
            self._setup_handlers()
            TelegramBot._initialized = True

    def _setup_handlers(self):
        @self.dp.message(Command('h'))
        async def send_welcome(message: types.Message):
            await message.reply(
                "📈 Stock Monitor Bot\n\n"
                "Available commands:\n"
                "/c - Get current status\n"
                "/d - Get divergent pairs\n"
                "/h - Show this help message"
            )

        @self.dp.message(Command('c'))
        async def status_command(message: types.Message):
            status = await self.monitor.get_all_signals()
            await message.reply(
                f"📊 Current Status\n{status}",
                parse_mode='HTML'
            )

        @self.dp.message(Command('d'))
        async def divergence_command(message: types.Message):
            all_signals = await self.monitor.get_all_signals(divergence_only=True)
            if all_signals:
                await message.reply(
                    f"📊 Divergent Pairs\n{all_signals}",
                    parse_mode='HTML'
                )
            else:
                await message.reply("No divergent pairs found at the moment.")

    async def _reset_webhook(self):
        try:
            await self.bot.delete_webhook()
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error resetting webhook: {str(e)}")

    async def start(self, pairs):
        await self._reset_webhook()
        logger.info("Telegram bot started")

    async def send_message(self, message: str, signal_pairs: list = None):
        try:
            if signal_pairs:
                chunk_size = 50
                for i in range(0, len(signal_pairs), chunk_size):
                    chunk = signal_pairs[i:i + chunk_size]
                    chunk_message = []
                    for pair, signal_info in chunk:
                        formatted_name = format_stock_name(pair.A_code)
                        chunk_message.append(f"<b>{formatted_name}</b>\n{signal_info}")
                    chunk_text = "\n".join(chunk_message)
                    full_message = f"{message}\n{chunk_text}" if message else chunk_text
                    if len(full_message) > 4096:
                        half = len(chunk) // 2
                        await self.send_message(message, chunk[:half])
                        await self.send_message(message, chunk[half:])
                        return
                    await self.bot.send_message(
                        chat_id=CHAT_ID,
                        text=full_message,
                        parse_mode='HTML'
                    )
                    await asyncio.sleep(0.5)
            else:
                await self.bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 실패: {str(e)}")
            raise

    async def start_polling(self):
        await self.dp.start_polling(self.bot, handle_signals=False)

    async def stop(self):
        try:
            await self.dp.stop_polling()
            await self.bot.session.close()
        except Exception as e:
            logger.error(f"Error stopping telegram bot: {str(e)}")