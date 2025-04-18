from aiogram import Bot, Dispatcher, types
from config import TELEGRAM_TOKEN, CHAT_ID
import logging
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import asyncio

logger = logging.getLogger(__name__)

class TelegramBot:
    _instance = None
    _initialized = False

    def strip_html_tags(text):
        """HTML 태그 제거 함수"""
        import re
        return re.sub(r'<[^>]+>', '', text) if text else text

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramBot, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not TelegramBot._initialized:
            self.bot = Bot(token=TELEGRAM_TOKEN)
            self.storage = MemoryStorage()
            self.dp = Dispatcher(self.bot, storage=self.storage)
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
            pairs = self.dp.bot.get('pairs')
            from main import StockMonitor
            monitor = StockMonitor()
            status = await monitor.get_all_signals()
            await message.reply(
                f"📊 Current Status\n{status}", 
                parse_mode='HTML'  # HTML 파싱 모드 추가
            )

        @self.dp.message_handler(commands=['d'])
        async def divergence_command(message: types.Message):
            pairs = self.dp.bot.get('pairs')
            from main import StockMonitor
            monitor = StockMonitor()
            all_signals = await monitor.get_all_signals(divergence_only=True)
            if all_signals:
                await message.reply(
                    f"📊 Divergent Pairs\n{all_signals}", 
                    parse_mode='HTML'  # HTML 파싱 모드 추가
                )
            else:
                await message.reply("No divergent pairs found at the moment.")

    async def _reset_webhook(self):
        try:
            # Delete webhook
            await self.bot.delete_webhook()
            # Wait a bit
            await asyncio.sleep(0.5)
            # Ensure there are no updates pending
            await self.bot.get_updates(offset=-1, timeout=1)
        except Exception as e:
            logger.error(f"Error resetting webhook: {str(e)}")
            raise

    async def start(self, pairs):
        try:
            # Reset webhook before starting
            await self._reset_webhook()
            self.dp.bot['pairs'] = pairs
            logger.info("Telegram bot started")
        except Exception as e:
            logger.error(f"Error starting telegram bot: {str(e)}")
            raise

    async def send_message(self, message: str):
        try:
            # HTML 태그 제거 코드 삭제
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,  # 원본 메시지 그대로 사용
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to send telegram message: {str(e)}")
            raise

    async def start_polling(self):
        try:
            # Reset webhook before polling
            await self._reset_webhook()
            # Start polling with clean state
            await self.dp.start_polling(reset_webhook=True, timeout=20, relax=0.1)
        except Exception as e:
            logger.error(f"Error in telegram polling: {str(e)}")
            raise

    async def stop(self):
        try:
            # Stop polling
            await self.dp.stop_polling()
            # Close storage
            await self.storage.close()
            await self.storage.wait_closed()
            # Close session
            session = await self.bot.get_session()
            if session:
                await session.close()
            # Clean up dispatcher
            await self.dp.storage.close()
            await self.dp.storage.wait_closed()
            # Reset webhook one last time
            await self._reset_webhook()
        except Exception as e:
            logger.error(f"Error stopping telegram bot: {str(e)}")
            raise