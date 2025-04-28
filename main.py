#!/usr/bin/env python3

import psutil
import asyncio
import logging
from typing import List, Tuple
from datetime import datetime, timedelta
import sys
from pathlib import Path
import json
import os
import sys
import fcntl
import atexit

from config import TICK_PAIRS, WAIT_TIME
from modules.pairs import NPPair
from modules.telegram import TelegramBot
from modules.utils import is_market_time
from modules.exceptions import MarketDataError

import logging
from logging.handlers import RotatingFileHandler
import os

# 로그 디렉토리 생성
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 로그 파일 경로
log_file = os.path.join(log_dir, 'stock_monitor.log')

# 로그 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 파일 핸들러 추가
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# 콘솔 핸들러 추가
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# 로그 테스트
logging.info("Logging initialized")

# 중복 실행 방지를 위한 락 파일 설정
def obtain_lock():
    lock_file_path = "/tmp/stmon_telegram.lock"
    try:
        # 락 파일이 이미 존재하고 다른 프로세스가 사용 중인지 확인
        if os.path.exists(lock_file_path):
            # 파일 내용 확인
            with open(lock_file_path, 'r') as f:
                pid = f.read().strip()
                # PID가 존재하는지 확인
                if pid and os.path.exists(f"/proc/{pid}"):
                    print(f"Another instance is already running with PID {pid}")
                    sys.exit(1)
                
        # 파일이 없거나 유효하지 않은 경우 새로 생성
        with open(lock_file_path, 'w') as f:
            f.write(str(os.getpid()))
        
        # 프로그램 종료 시 락 파일 제거
        def cleanup():
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
        
        atexit.register(cleanup)
        return True
    except Exception as e:
        print(f"Error obtaining lock: {e}")
        return False

# 프로그램 시작 시 락 확인
if not obtain_lock():
    print("Failed to obtain lock. Another instance might be running.")
    sys.exit(1)
    
def ensure_single_instance():
        script_name = os.path.basename(sys.argv[0])
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.name() == 'python3' and script_name in proc.cmdline() and proc.pid != os.getpid():
                    print(f"Terminating existing instance with PID {proc.pid}")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path('logs/stock_monitor.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def mark_special_stocks(stock_name):
    """
    특별 관심 종목에 아이콘 표시하고 가중치 정보 포함한 종목명 반환
    이 함수는 특별 관심 종목들을 그룹으로 나누어 다른 아이콘으로 표시합니다.
    또한 가중치 정보를 새로운 형식(-0.5- 등)으로 변환합니다.
    """
    # 종목 기본명과 가중치 추출
    base_name = stock_name
    weight_info = None
    
    if ' (' in stock_name and ')' in stock_name:
        parts = stock_name.split(' (')
        if len(parts) == 2 and ')' in parts[1]:
            base_name = parts[0]
            weight_info = parts[1].replace(')', '')
    
    # 특별 관심 종목 그룹 1 (빨간색 아이콘)
    special_stocks_1 = [
        '삼성전자', '현대차', 'S-Oil', '한진칼', 'SK'
    ]
    
    # 특별 관심 종목 그룹 2 (주황색 아이콘)
    special_stocks_2 = [
        '한국금융지주', '티와이홀딩스', '삼성화재', '호텔신라', 'SK이노베이션',
        'GS', 'CJ제일제당', 'SK디스커버리', '롯데지주', '깨끗한나라', 
        '부국증권', '하이트진로홀딩스'
    ]
    
    # 특별 관심 종목 그룹 3 (녹색 아이콘)
    special_stocks_3 = [
        '코오롱모빌리티그룹', '태양금속', '코오롱', '성신양회', '코오롱글로벌',
        '신풍제약', '한화솔루션', '한화투자증권', 'LG화학', '두산', 
        '남선알미늄', '대원전선', '대호특수강', '한양증권', '노루페인트', 
        '크라운해태홀딩스', '롯데칠성', '일양약품', '삼양사', 'JW중외제약', '삼양홀딩스'
    ]
    
    # 특별 관심 종목 그룹 4 (파란색 아이콘)
    special_stocks_4 = [
        'NH투자증권', 'LG전자', 'LG생활건강', '아모레G', '대한항공',
        '미래에셋증권', '금호석유', 'SK케미칼', '삼성전기', 'LG', 
        '삼성SDI', '코오롱인더', '현대건설', 'DL이앤씨', '대상', 
        'DL', 'CJ', '유한양행', 'BYC'
    ]
    
    # 아이콘 추가 및 가중치 정보 포맷 변경
    result = base_name
    if weight_info:
        # 괄호 대신 대시 형식으로 변경
        result = f"{base_name}-{weight_info}-"
    
    # 기본명으로 종목 확인 및 아이콘 추가
    if base_name in special_stocks_1:
        return f'🔴 {result}'
    elif base_name in special_stocks_2:
        return f'🟠 {result}'
    elif base_name in special_stocks_3:
        return f'🟢 {result}'
    elif base_name in special_stocks_4:
        return f'🔵 {result}'
    else:
        return result

class StockMonitor:
    def __init__(self):
        self.pairs: List[NPPair] = [NPPair(*pair) for pair in TICK_PAIRS]
        self.telegram_bot = TelegramBot()
        self.running = True
        self.last_r_signal_time = {}  # 종목별 마지막 R 신호 시간 추적
            
    async def get_signals_with_divergent(self) -> Tuple[str, str]:
        try:
            # 배치 크기 설정 (한 번에 처리할 페어 수)
            batch_size = 5
            all_results = []
            
            # 페어를 배치로 나누어 처리
            for i in range(0, len(self.pairs), batch_size):
                logger.info(f"처리 중인 배치: {i+1}~{min(i+batch_size, len(self.pairs))} / {len(self.pairs)}")
                batch_pairs = self.pairs[i:i+batch_size]
                batch_tasks = [asyncio.create_task(pair.get_signal_now()) for pair in batch_pairs]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # 결과 처리
                for pair, result in zip(batch_pairs, batch_results):
                    all_results.append((pair, result))
                
                # 배치 간 딜레이 추가
                if i + batch_size < len(self.pairs):
                    await asyncio.sleep(3)  # 배치 간 3초 대기
            
            all_messages = []
            divergent_messages = []
            r_signal_pairs = []  # 'R' 신호 페어 추적
            
            for pair, result in all_results:
                # 종목명에 HTML 태그가 없도록 깨끗하게 추출
                clean_name = mark_special_stocks(pair.A_name)
                
                # 깨끗한 종목명을 <b> 태그로 감싸기
                formatted_name = f"<b>{clean_name}</b>"
                
                if isinstance(result, Exception):
                    logger.error(f"Error getting signal for {pair.A_name}: {str(result)}")
                    all_messages.append(f"{formatted_name}\n    Error - {str(result)}")
                elif result:
                    signal_info = result
                    all_messages.append(f"{formatted_name}\n    {signal_info}")
                    
                    # sz 값이 2를 넘는지 확인
                    try:
                        sz_value = float(signal_info.split('/')[0].strip())
                        if sz_value >= 2:
                            divergent_messages.append(f"{formatted_name}\n    {signal_info}")
                    
                        # 'R' 신호 확인
                        if 'R' in signal_info.split('/')[1]:
                            r_signal_pairs.append((pair, signal_info))
                    except (ValueError, IndexError):
                        continue
                else:
                    all_messages.append(f"{formatted_name}\n    No signal")
            
            # 'R' 신호 메시지 처리도 동일하게 수정
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
                        # 깨끗한 종목명 추출
                        clean_name = mark_special_stocks(pair.A_name)
                        formatted_name = f"<b>{clean_name}</b>"

                        r_message = (
                            f"🚨 <b>R Signal Detected</b>\n"
                            f"{formatted_name}\n"
                            f"     {signal_info}\n"
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
                    f"🕒 {current_time}\n"
                    f"📊 Current Status\n{all_signals}\n\n"
                    f"🚨 Divergent Pairs\n{divergent_signals}"
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
    ensure_single_instance()  # 중복 프로세스 종료
    asyncio.run(main())
    