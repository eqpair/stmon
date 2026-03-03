#!/usr/bin/env python3

import os
import sys
import psutil
import atexit
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from pathlib import Path
import json
import subprocess

import aiohttp
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup

from config import TICK_PAIRS, WAIT_TIME
from modules.pairs import NPPair
from modules.utils import is_market_time, safe_json_dump

# 로그 디렉토리 생성
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'stock_monitor.log')

# 로그 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)
logging.info("Logging initialized")

def obtain_lock():
    lock_file_path = "/tmp/stmon_telegram.lock"
    try:
        if os.path.exists(lock_file_path):
            with open(lock_file_path, 'r') as f:
                pid = f.read().strip()
            if pid and os.path.exists(f"/proc/{pid}"):
                print(f"Another instance is already running with PID {pid}")
                sys.exit(1)
        with open(lock_file_path, 'w') as f:
            f.write(str(os.getpid()))
        def cleanup():
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
        atexit.register(cleanup)
        return True
    except Exception as e:
        print(f"Error obtaining lock: {e}")
        return False

if not obtain_lock():
    print("Failed to obtain lock. Another instance might be running.")
    sys.exit(1)

def ensure_single_instance():
    script_name = os.path.basename(sys.argv[0])
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.name() == 'python3' and proc.pid != os.getpid():
                for cmd in proc.cmdline():
                    if os.path.basename(cmd) == script_name:
                        print(f"Terminating existing instance with PID {proc.pid}")
                        proc.kill()
                        break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

# 종목명 가중치 및 아이콘 표시
def mark_special_stocks(stock_name):
    """
    종목명을 받아서 포맷팅된 종목명 반환
    이 함수는 호환성을 위해 유지하지만, 내부적으로는 format_stock_name 사용
    """
    from modules.utils import format_stock_name
    
    # 종목 코드 추출 시도
    code = None
    
    # 종목명에서 코드를 추출하는 로직 (기존 코드에 없다면 추가)
    # 예: "삼성전자 (0.5 [2.3])" -> "005930"
    # 이 부분은 코드 추출 로직이 필요하나, 여기서는 단순화를 위해 생략
    
    # 코드를 알 수 없는 경우 원래 이름 반환
    if not code:
        return stock_name
    
    return format_stock_name(code)


# 신호 텍스트를 웹용 JSON으로 파싱
# 기존 함수 전체를 아래로 교체
def parse_signals(signals_text):
    import re
    result = []
    if not signals_text or "No divergent pairs" in signals_text:
        return result
    lines = signals_text.split('\n')
    i = 0
    while i < len(lines) - 1:
        stock_name_line = re.sub(r'<[^>]+>', '', lines[i].strip())
        signal_line = lines[i+1].strip() if i+1 < len(lines) else ""
        if not stock_name_line or not signal_line:
            i += 2
            continue
        sz_value = 0.0
        signal = ""
        price_a, price_b = None, None
        skew_long, skew_short = None, None  # 추가

        signal_parts = signal_line.split('/')
        try:
            sz_value = float(signal_parts[0].strip())
        except:
            sz_value = 0.0
        if len(signal_parts) > 1:
            signal = signal_parts[1].strip()
        if len(signal_parts) > 2:
            price_items = signal_parts[2].strip().split(',')
            if len(price_items) > 0:
                try: price_a = float(price_items[0].strip())
                except: pass
            if len(price_items) > 1:
                try: price_b = float(price_items[1].strip())
                except: pass
        # 추가: 왜도 파싱 (signal_parts[3])
        if len(signal_parts) > 3:
            try:
                skew_long = float(signal_parts[3].replace('SKW', '').strip())
                skew_short = float(signal_parts[4].strip()) if len(signal_parts) > 4 else None
            except:
                pass

        signal_data = {
            "stock_name": stock_name_line,
            "sz_value": sz_value,
            "signal": signal,
            "price_a": price_a,
            "price_b": price_b,
            "skew_long": skew_long,    # 추가
            "skew_short": skew_short,  # 추가
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        result.append(signal_data)
        i += 2
    return result

# 웹 데이터 파일 저장
def save_web_data(all_signals, divergent_signals):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "timestamp": current_time,
        "last_updated": current_time,
        "all_signals": parse_signals(all_signals),
        "divergent_signals": parse_signals(divergent_signals)
    }
    safe_json_dump(data, "data/stock_data.json")

# 트렌드 데이터 수집 및 저장
async def collect_all_trends(pairs):
    TRENDS_DIR = Path("data/trends")
    TRENDS_DIR.mkdir(parents=True, exist_ok=True)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        for pair in pairs:
            days_to_fetch = 365
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_to_fetch)
            a_data = await fetch_stock_history(session, pair.A_code, start_date, days_to_fetch+30)
            b_data = await fetch_stock_history(session, pair.B_code, start_date, days_to_fetch+30)
            if not a_data or not b_data:
                logger.warning(f"트렌드 데이터 수집 실패: {pair.A_name}")
                continue
            result = process_trend_data(pair, a_data, b_data)
            if result:
                file_path = TRENDS_DIR / f"{pair.A_code}.json"
                safe_json_dump(result, file_path)
                logger.info(f"{pair.A_name} 트렌드 데이터 저장 완료")

async def fetch_stock_history(session, stock_code, start_date, days):
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={stock_code}&timeframe=day&startTime={start_date.strftime('%Y%m%d')}&count={days}&requestType=0"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status != 200:
                return None
            return await response.text()
    except Exception as e:
        logger.warning(f"{stock_code} 데이터 수집 실패: {e}")
        return None

def process_trend_data(pair, a_data, b_data):
    try:
        a_df = parse_stock_data(a_data, pair.A_code)
        b_df = parse_stock_data(b_data, pair.B_code)
        if a_df is None or b_df is None or a_df.empty or b_df.empty:
            return None
        merged_df = pd.merge(a_df, b_df, left_index=True, right_index=True, suffixes=('_A', '_B'))
        merged_df['dr'] = (merged_df['close_A'] - merged_df['close_B']) / merged_df['close_A']
        merged_df['dr_avg'] = merged_df['dr'].rolling(window=pair.avg_period).mean().shift(1)
        merged_df['std'] = merged_df['dr'].rolling(window=pair.avg_period).std().shift(1)
        merged_df['sz'] = (merged_df['dr'] - merged_df['dr_avg']) / merged_df['std']
        result = {
            'stock_code': pair.A_code,
            'stock_name': pair.A_name,
            'dates': merged_df.index.strftime('%Y-%m-%d').tolist(),
            'common_prices': [None if pd.isna(x) else float(x) for x in merged_df['close_A'].tolist()],
            'preferred_prices': [None if pd.isna(x) else float(x) for x in merged_df['close_B'].tolist()],
            'discount_rates': [None if pd.isna(x) else float(x) for x in merged_df['dr'].tolist()],
            'sz_values': [None if pd.isna(x) else float(x) for x in merged_df['sz'].tolist()],
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return result
    except Exception as e:
        logger.warning(f"트렌드 데이터 처리 오류: {e}")
        return None

def parse_stock_data(data, code):
    try:
        soup = BeautifulSoup(data, 'html.parser')
        chartdata = soup.find('chartdata')
        if chartdata is None:
            return None
        name = chartdata.get('name', code)
        items = soup.find_all('item')
        if not items:
            return None
        dates, closes = [], []
        for item in items:
            if 'data' not in item.attrs:
                continue
            d = item['data'].split('|')
            if len(d) >= 5:
                try:
                    dates.append(pd.to_datetime(d[0]))
                    closes.append(float(d[4]))
                except:
                    continue
        if not dates or not closes:
            return None
        df = pd.DataFrame({'close': closes}, index=dates)
        df.name = name
        return df
    except Exception as e:
        logger.warning(f"주식 데이터 파싱 오류: {e}")
        return None

# GitHub 커밋 및 푸시
def commit_and_push_github(repo_path, commit_message=None):
    if commit_message is None:
        commit_message = f"데이터 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    os.chdir(repo_path)
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
    if not status.stdout.strip():
        logger.info("변경사항 없음, git push 생략")
        return
    subprocess.run("git add .", shell=True, check=True)
    subprocess.run(f'git commit -m "{commit_message}"', shell=True, check=True)
    subprocess.run("git push", shell=True, check=True)
    logger.info("GitHub 저장소에 성공적으로 푸시되었습니다.")

class StockMonitor:
    def __init__(self):
        from modules.telegram import TelegramBot
        self.pairs = [NPPair(*pair) for pair in TICK_PAIRS]
        self.telegram_bot = TelegramBot(self)  # monitor 인스턴스를 넘김!
        self.running = True
        self.last_r_signal_time = {}

    async def get_signals_with_divergent(self):
        try:
            batch_size = 5
            all_results = []

            for i in range(0, len(self.pairs), batch_size):
                logger.info(f"처리 중인 배치: {i+1}~{min(i+batch_size, len(self.pairs))} / {len(self.pairs)}")
                batch_pairs = self.pairs[i:i+batch_size]
                batch_tasks = [asyncio.create_task(pair.get_signal_now()) for pair in batch_pairs]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                for pair, result in zip(batch_pairs, batch_results):
                    all_results.append((pair, result))

                if i + batch_size < len(self.pairs):
                    await asyncio.sleep(3)

            all_messages = []
            divergent_messages = []

            in_signal_pairs = []
            out_signal_pairs = []
            chk_signal_pairs = []

            for pair, result in all_results:
                formatted_name = f"<b>{pair.A_name}</b>"
                if isinstance(result, Exception):
                    logger.error(f"Error getting signal for {pair.A_name}: {str(result)}")
                    continue  # 신호 없는 종목은 웹에 저장하지 않음!    
                elif result:
                    signal_info = result
                    all_messages.append(f"{formatted_name}\n{signal_info}")

                    try:
                        # sz, 신호명, 가격정보 파싱
                        signal_parts = signal_info.split('/')
                        sz_value = float(signal_parts[0].strip())
                        signal_type = signal_parts[1].strip()
                        # sl_in, sl_out은 pair 객체의 값 사용
                        sl_in = pair.SL_in_val
                        sl_out = pair.SL_out_val

                        # divergent 기준: sz ≥ sl_in
                        if sz_value >= sl_in:
                            divergent_messages.append(f"{formatted_name}\n {signal_info}")

                        # 신호명 분류(혹시 신호 생성부에서 잘못된 값이 들어올 때도 sl_in/sl_out 기준으로 재분류)
                        if sz_value >= sl_in:
                            in_signal_pairs.append((pair, signal_info))
                        elif sz_value <= sl_out:
                            out_signal_pairs.append((pair, signal_info))
                        else:
                            chk_signal_pairs.append((pair, signal_info))
                    except (ValueError, IndexError):
                        continue
                else:
                    continue  # 신호 없는 종목은 웹에 저장하지 않음!

            # IN 신호 텔레그램 알림
            for pair, signal_info in in_signal_pairs:
                try:
                    parts = signal_info.split('/')
                    sz = float(parts[0].strip())
                    current_time = datetime.now()
                    last_signal_time = self.last_r_signal_time.get(pair.A_name)
                    # 1시간 이내 중복 알림 방지
                    if (not last_signal_time) or (current_time - last_signal_time > timedelta(hours=1)):
                        clean_name = mark_special_stocks(pair.A_name)
                        formatted_name = f"<b>{clean_name}</b>"
                        in_message = (
                            f"🚨 IN Signal Detected\n"
                            f"{formatted_name}\n"
                            f" {signal_info}\n"
                        )
                        await self.telegram_bot.send_message(in_message)
                        self.last_r_signal_time[pair.A_name] = current_time
                except Exception as e:
                    logger.error(f"Error processing IN signal for {pair.A_name}: {str(e)}")

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
        GITHUB_REPO_PATH = os.environ.get('GITHUB_REPO_PATH', '/home/eq/stmon')
        while self.running:
            try:
                if not is_market_time():
                    await asyncio.sleep(60)
                    continue
                logger.info("Fetching signals for periodic update...")
                all_signals, divergent_signals = await self.get_signals_with_divergent()

                # 신호 페어 리스트 생성
                all_signal_pairs = []
                for pair, result in await self.get_signals_with_divergent_pairs():
                    if isinstance(result, Exception) or not result:
                        continue
                    all_signal_pairs.append((pair, result))

                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message = (
                    f"🕒 {current_time}\n"
                    f"📊 Current Status"
                )
                # 종목 신호를 50개씩 나누어 전송
                await self.telegram_bot.send_message(message, all_signal_pairs)

                # Divergent 신호 전송
                divergent_signal_pairs = [
                    (pair, result) for pair, result in all_signal_pairs
                    if result and float(result.split('/')[0].strip()) >= pair.SL_in_val
                ]
                if divergent_signal_pairs:
                    divergent_message = f"🕒 {current_time}\n🚨 Divergent Pairs"
                    await self.telegram_bot.send_message(divergent_message, divergent_signal_pairs)
                else:
                    await self.telegram_bot.send_message(f"🕒 {current_time}\n🚨 No divergent pairs found.")

                logger.info("Periodic update sent successfully")
                # 웹 데이터 파일 저장
                save_web_data(all_signals, divergent_signals)
                # 트렌드 데이터 수집 및 저장
                await collect_all_trends(self.pairs)
                # GitHub 커밋/푸시
                commit_and_push_github(GITHUB_REPO_PATH)
                await asyncio.sleep(WAIT_TIME)
            except Exception as e:
                logger.error(f"Error in periodic update: {str(e)}")
                await asyncio.sleep(30)
    async def get_signals_with_divergent_pairs(self):
        try:
            batch_size = 5
            all_results = []

            for i in range(0, len(self.pairs), batch_size):
                logger.info(f"처리 중인 배치: {i+1}~{min(i+batch_size, len(self.pairs))} / {len(self.pairs)}")
                batch_pairs = self.pairs[i:i+batch_size]
                batch_tasks = [asyncio.create_task(pair.get_signal_now()) for pair in batch_pairs]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                for pair, result in zip(batch_pairs, batch_results):
                    all_results.append((pair, result))

                if i + batch_size < len(self.pairs):
                    await asyncio.sleep(3)

            return all_results
        except Exception as e:
            logger.error(f"Error in get_signals_with_divergent_pairs: {str(e)}")
            raise
            
    async def start(self):
        logger.info("Starting Stock Monitor...")
        await self.telegram_bot.start(self.pairs)
        update_task = asyncio.create_task(self.send_periodic_updates())
        polling_task = asyncio.create_task(self.telegram_bot.start_polling())
        await asyncio.gather(update_task, polling_task)

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
    ensure_single_instance()
    asyncio.run(main())