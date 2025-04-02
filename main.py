#!/usr/bin/env python3

import os
import sys
import fcntl
import logging
from logging.handlers import RotatingFileHandler
import asyncio
import logging
from typing import List, Tuple
from datetime import datetime, timedelta
import sys
from pathlib import Path
import json

from config import TICK_PAIRS, WAIT_TIME
from modules.pairs import NPPair
from modules.telegram import TelegramBot
from modules.utils import is_market_time
from modules.exceptions import MarketDataError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path('logs/stock_monitor.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 단일 인스턴스 실행 보장
def single_instance(lockfile):
    try:
        fp = open(lockfile, 'w')
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, BlockingIOError):
        print("다른 인스턴스가 실행 중입니다. 종료합니다.")
        sys.exit(1)
    return fp

# 로깅 설정
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 콘솔 로그
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 파일 로그 (최대 10MB, 5개 백업)
    file_handler = RotatingFileHandler(
        'bot.log', 
        maxBytes=10*1024*1024,  
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    
    # 로그 포맷
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

# 스크립트 시작 부분
lock_file = '/tmp/bot_instance.lock'
lock = single_instance(lock_file)
setup_logging()

def mark_special_stocks(stock_name):
    special_stocks_1 = ['삼성전자', '현대차', 'S-Oil', '한진칼', 'SK']
    special_stocks_2 = ['한국금융지주', '티와이홀딩스', '삼성화재', '호텔신라', 'SK이노베이션', 'GS', 'CJ제일제당', 'SK디스커버리', '롯데지주', '깨끗한나라', '부국증권', '하이트진로홀딩스']
    special_stocks_3 = ['코오롱모빌리티그룹', '태양금속', '코오롱', '성신양회', '코오롱글로벌', '신풍제약', '한화솔루션', '한화투자증권', 'LG화학', '두산', '남선알미늄', '대원전선', '대호특수강', '한양증권', '노루페인트', '크라운해태홀딩스', '롯데칠성', '일양약품', '삼양사', 'JW중외제약', '삼양홀딩스']
    
    if stock_name in special_stocks_1:
        return f'🔴 {stock_name}'
    elif stock_name in special_stocks_2:
        return f'🟠 {stock_name}'
    elif stock_name in special_stocks_3:
        return f'🟢 {stock_name}'
    else:
        return stock_name

class StockMonitor:
    def __init__(self):
        self.pairs: List[NPPair] = [NPPair(*pair) for pair in TICK_PAIRS]
        self.telegram_bot = TelegramBot()
        self.running = True
        self.last_r_signal_time = {}  # 종목별 마지막 R 신호 시간 추적
        
    async def get_signals_with_divergent(self) -> Tuple[str, str]:
        try:
            tasks = [asyncio.create_task(pair.get_signal_now()) for pair in self.pairs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            all_messages = []
            divergent_messages = []
            r_signal_pairs = []  # 'R' 신호 페어 추적
            
            for pair, result in zip(self.pairs, results):
                if isinstance(result, Exception):
                    logger.error(f"Error getting signal for {pair.A_name}: {str(result)}")
                    all_messages.append(f"{mark_special_stocks(pair.A_name)}: Error - {str(result)}")
                elif result:
                    signal_info = result
                    all_messages.append(f"{mark_special_stocks(pair.A_name)}: {signal_info}")
                    
                    # sz 값이 2를 넘는지 확인
                    try:
                        sz_value = float(signal_info.split('/')[0].strip())
                        if sz_value >= 2:
                            divergent_messages.append(f"{mark_special_stocks(pair.A_name)}: {signal_info}")
                        
                        # 'R' 신호 확인
                        if 'R' in signal_info.split('/')[1]:
                            r_signal_pairs.append((pair, signal_info))
                    except (ValueError, IndexError):
                        continue
                else:
                    all_messages.append(f"{mark_special_stocks(pair.A_name)}: No signal")
            
            # 'R' 신호 페어에 대한 추가 메시지 처리
            for pair, signal_info in r_signal_pairs:
                try:
                    # 신호 정보 파싱
                    parts = signal_info.split('/')
                    sz = float(parts[0].strip())
                    
                    # 해당 종목의 마지막 R 신호 시간 확인
                    current_time = datetime.now()
                    last_signal_time = self.last_r_signal_time.get(pair.A_name)
                    # 마지막 신호 시간이 없거나 1시간 이상 지났다면 메시지 전송
                    if (not last_signal_time) or (current_time - last_signal_time > timedelta(hours=1)):
                        r_message = (
                            f"🚨 R Signal Detected\n"
                            f"{pair.A_name}\n"
                            f"{signal_info}\n"
                    )
                    
                    # 텔레그램으로 R 신호 메시지 전송
                        await self.telegram_bot.send_message(r_message)
                    
                    # 마지막 R 신호 시간 업데이트
                        self.last_r_signal_time[pair.A_name] = current_time
                    
                except Exception as e:
                    logger.error(f"Error processing R signal for {pair.A_name}: {str(e)}")
            
            all_signals = "\n".join(all_messages)
            divergent_signals = "\n".join(divergent_messages) if divergent_messages else "No divergent pairs found at the moment."
            
            return all_signals, divergent_signals
                    
        except Exception as e:
            logger.error(f"Error in get_signals_with_divergent: {str(e)}")
            raise

    async def get_all_signals(self, divergence_only: bool = False) -> str:
        try:
            all_signals, divergent_signals = await self.get_signals_with_divergent()
            return divergent_signals if divergence_only else all_signals
        except Exception as e:
            logger.error(f"Error in get_all_signals: {str(e)}")
            raise

    async def send_periodic_updates(self):
        while self.running:
            try:
                if not is_market_time():
                    await asyncio.sleep(60)
                    continue
                
                logger.info("Fetching signals for periodic update...")
                all_signals, divergent_signals = await self.get_signals_with_divergent()
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                message = (
                    f"🕒 {current_time}\n\n"
                    f"📊 Current Status\n\n{all_signals}\n\n"
                    f"🚨 Divergent Pairs\n\n{divergent_signals}"
                )
                
                await self.telegram_bot.send_message(message)
                logger.info("Periodic update sent successfully")
                
                await asyncio.sleep(WAIT_TIME)
            except Exception as e:
                logger.error(f"Error in periodic update: {str(e)}")
                await asyncio.sleep(30)

    async def start(self):
        try:
            logger.info("Starting Stock Monitor...")
            await self.telegram_bot.start(self.pairs)
            
            update_task = asyncio.create_task(self.send_periodic_updates())
            polling_task = asyncio.create_task(self.telegram_bot.start_polling())
            
            await asyncio.gather(update_task, polling_task)
        except Exception as e:
            logger.error(f"Critical error in Stock Monitor: {str(e)}")
            self.running = False
            raise

    async def shutdown(self):
        logger.info("Shutting down Stock Monitor...")
        self.running = False
        await self.telegram_bot.stop()

async def main():
    monitor = StockMonitor()
    try:
        await monitor.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await monitor.shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        await monitor.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())