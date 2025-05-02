from aiogram import Bot, Dispatcher, types
import logging
import os
from config import TELEGRAM_TOKEN, CHAT_ID
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import asyncio

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
            self.dp = Dispatcher(self.bot, storage=self.storage)
            self.monitor = monitor  # StockMonitor 인스턴스 저장!
            self._setup_handlers()
            TelegramBot._initialized = True

    def _setup_handlers(self):
        @self.dp.message_handler(commands=['h'])
        async def send_welcome(message: types.Message):
            await message.reply(
                "📈 Stock Monitor Bot\n\n"
                "Available commands:\n"
                "/c - Get current status\n"
                "/d - Get divergent pairs\n"
                "/h - Show this help message"
            )

        @self.dp.message_handler(commands=['c'])
        async def status_command(message: types.Message):
            status = await self.monitor.get_all_signals()
            await message.reply(
                f"📊 Current Status\n{status}",
                parse_mode='HTML'
            )

        @self.dp.message_handler(commands=['d'])
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
            await self.bot.get_updates(offset=-1, timeout=1)
        except Exception as e:
            logger.error(f"Error resetting webhook: {str(e)}")
            raise

    async def start(self, pairs):
        await self._reset_webhook()
        self.dp.bot['pairs'] = pairs
        logger.info("Telegram bot started")

    async def send_message(self, message: str):
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to send telegram message: {str(e)}")
            raise

    async def start_polling(self):
        await self.dp.start_polling(reset_webhook=True, timeout=20, relax=0.1)

    async def stop(self):
        try:
            await self.dp.stop_polling()
            await self.storage.close()
            await self.storage.wait_closed()
            session = await self.bot.get_session()
            if session:
                await session.close()
            await self.dp.storage.close()
            await self.dp.storage.wait_closed()
            await self._reset_webhook()
        except Exception as e:
            logger.error(f"Error stopping telegram bot: {str(e)}")
            raise
