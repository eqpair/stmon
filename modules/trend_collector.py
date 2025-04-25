#!/usr/bin/env python3

import asyncio
import aiohttp
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from config import TICK_PAIRS
from modules.pairs import NPPair
from modules.utils import safe_json_dump

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trend_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 기본 데이터 디렉토리
DATA_DIR = Path("data")
TRENDS_DIR = DATA_DIR / "trends"
os.makedirs(TRENDS_DIR, exist_ok=True)

class TrendCollector:
    def __init__(self):
        self.pairs = [NPPair(*pair) for pair in TICK_PAIRS]
        self._session = None

    async def _get_session(self):
        connector = aiohttp.TCPConnector(ssl=False)  # SSL 검증 비활성화
        return aiohttp.ClientSession(connector=connector)

#    async def _get_session(self):
#        if self._session is None or self._session.closed:
#            self._session = aiohttp.ClientSession()
#        return self._session

    async def collect_all_trends(self):
        """모든 종목의 트렌드 데이터 수집"""
        logger.info("트렌드 데이터 수집 시작...")
        
        # 배치 크기 정의
        batch_size = 3 # 한 번에 3개씩 처리
        success_count = 0
        error_count = 0
        
        # 배치 단위로 처리
        for i in range(0, len(self.pairs), batch_size):
            batch = self.pairs[i:i+batch_size]
            batch_tasks = []
            
            for pair in batch:
                task = asyncio.create_task(self.collect_trend_data(pair))
                batch_tasks.append(task)
            
            # 현재 배치 실행
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # 결과 처리
            batch_success = sum(1 for r in batch_results if not isinstance(r, Exception))
            batch_error = len(batch_results) - batch_success
            success_count += batch_success
            error_count += batch_error
            
            # 다음 배치 전 대기
            if i + batch_size < len(self.pairs):
                logger.info(f"배치 처리 완료: {i+1}~{i+len(batch)} / {len(self.pairs)}")
                await asyncio.sleep(5) # 배치 사이 5초 대기
        
        logger.info(f"트렌드 데이터 수집 완료: 성공 {success_count}개, 실패 {error_count}개")

    async def collect_trend_data(self, pair):
        """특정 종목 페어의 트렌드 데이터 수집"""
        session = None
        try:
            # 세션 가져오기 (SSL 검증 비활성화)
            session = await self._get_session()
            
            days_to_fetch = 365
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_to_fetch)
            
            # A/B 종목 데이터 수집 (병렬 처리)
            a_data, b_data = await asyncio.gather(
                self._fetch_stock_history(session, pair.A_code, start_date, days_to_fetch+30),
                self._fetch_stock_history(session, pair.B_code, start_date, days_to_fetch+30)
            )
            
            # 데이터 유효성 검사 강화
            if not a_data or not b_data:
                logger.error(f"데이터 수신 실패: A={bool(a_data)}, B={bool(b_data)}")
                return False
                
            # 데이터 처리 및 저장
            result = self._process_trend_data(pair, a_data, b_data)
            
            if result:
                self._save_trend_data(pair.A_code, result)
                logger.info(f"{pair.A_name} 트렌드 데이터 수집 완료 (1년치)")
                return True
                
        except Exception as e:
            logger.error(f"{pair.A_name} 트렌드 데이터 수집 중 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
        finally:
            if session and not session.closed:
                await session.close()
        return False


    async def _fetch_stock_history(self, session, stock_code, start_date, days):
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={stock_code}&timeframe=day&startTime={start_date.strftime('%Y%m%d')}&count={days}&requestType=0"
        
        # 재시도 로직 추가
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"API 응답 오류 ({stock_code}): HTTP {response.status}")
                        return None
                    
                    content = await response.text()
                    if not content:
                        logger.warning(f"빈 응답 수신 ({stock_code})")
                        return None
                    
                    return content
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"최종 시도 실패 ({stock_code}): {str(e)}")
                    return None
                await asyncio.sleep(2 ** attempt)  # 지수 백오프

    def _process_trend_data(self, pair, a_data, b_data):
        try:
            # 데이터 파싱
            a_df = self._parse_stock_data(a_data, pair.A_code)
            b_df = self._parse_stock_data(b_data, pair.B_code)
            
            if a_df is None or b_df is None or a_df.empty or b_df.empty:
                logger.warning(f"{pair.A_name} 데이터 파싱 실패")
                return None
            
            # 데이터 병합
            merged_df = pd.merge(a_df, b_df, left_index=True, right_index=True, suffixes=('_A', '_B'))
            
            # 괴리율 계산
            merged_df['dr'] = (merged_df['close_A'] - merged_df['close_B']) / merged_df['close_A']
            
            # 이동평균 계산
            merged_df['dr_avg'] = merged_df['dr'].rolling(window=pair.avg_period).mean().shift(1)
            
            # 표준편차 계산
            merged_df['std'] = merged_df['dr'].rolling(window=pair.avg_period).std().shift(1)
            
            # SZ 값 계산
            merged_df['sz'] = (merged_df['dr'] - merged_df['dr_avg']) / merged_df['std']
            
            # 결과 데이터 생성 시 직접 NaN 값을 변환
            result = {
                'stock_code': pair.A_code,
                'stock_name': pair.A_name,
                'dates': merged_df.index.strftime('%Y-%m-%d').tolist(),
                'common_prices': [None if pd.isna(x) else float(x) for x in merged_df['close_A'].tolist()],
                'preferred_prices': [None if pd.isna(x) else float(x) for x in merged_df['close_B'].tolist()],
                'discount_rates': [None if pd.isna(x) else float(x) for x in merged_df['dr'].tolist()],
                'sz_values': [None if pd.isna(x) else float(x) for x in merged_df['sz'].tolist()],
                'signals': self._generate_signals(merged_df, pair),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return result
            
        except Exception as e:
            logger.error(f"{pair.A_name} 트렌드 데이터 처리 중 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _generate_signals(self, data, pair=None):
        signals = []
        
        for i in range(1, len(data)):
            last_row = data.iloc[i]
            prev_row = data.iloc[i-1]
            sz = last_row['sz']
            
            # 신호 생성 로직 통일
            signal = ''
            if sz >= 2.0:
                signal += 'R'
            if sz >= 1.5 and sz < 2.5:
                signal += 'I'
            if sz < 0.5:
                signal += 'O'
            
            if signal: # 비어있지 않은 경우에만 신호 추가
                signal_entry = {
                    'timestamp': last_row.name.strftime('%Y-%m-%d %H:%M:%S'),
                    'sz_value': sz,
                    'signal': signal,
                    'price_a': last_row['close_A'],
                    'price_b': last_row['close_B']
                }
                signals.append(signal_entry)
        
        return signals

    def _parse_stock_data(self, data, code):
        """주식 데이터 파싱"""
        try:
            soup = BeautifulSoup(data, 'html.parser')
            chartdata = soup.find('chartdata')
            
            if chartdata is None:
                logger.warning(f"{code} 차트 데이터를 찾을 수 없음")
                return None
            
            # chartdata에서 name 속성을 찾고, 없으면 code를 사용
            name = chartdata.get('name', code)
            
            # item들을 찾음
            items = soup.find_all('item')
            
            if not items:
                logger.warning(f"{code} 아이템 데이터 없음")
                return None
            
            dates = []
            closes = []
            
            for item in items:
                if 'data' not in item.attrs:
                    continue
                
                data = item['data'].split('|')
                
                if len(data) >= 5: # 데이터가 충분한지 확인
                    try:
                        dates.append(pd.to_datetime(data[0]))
                        closes.append(float(data[4]))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"{code} 잘못된 데이터 형식 무시: {str(e)}")
                        continue
            
            if not dates or not closes:
                logger.warning(f"{code} 유효한 데이터 없음")
                return None
            
            df = pd.DataFrame({'close': closes}, index=dates)
            df.name = name
            
            return df
            
        except Exception as e:
            logger.error(f"{code} 데이터 파싱 중 오류: {str(e)}")
            return None

    def _save_trend_data(self, stock_code, data):
        """트렌드 데이터 저장"""
        file_path = TRENDS_DIR / f"{stock_code}.json"
        try:
            # 여기서 한 번만 호출
            safe_json_dump(data, file_path)
            logger.info(f"트렌드 데이터 저장 성공: {file_path}")
            
            # 파일 존재 및 크기 확인
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                logger.info(f"파일 크기: {file_size} 바이트")
            else:
                logger.warning(f"파일 생성 실패: {file_path}")
        except Exception as e:
            logger.error(f"트렌드 데이터 저장 실패 ({stock_code}): {str(e)}")
            raise
        
        # 이 부분 제거 - 중복 호출
        # from modules.utils import safe_json_dump
        # safe_json_dump(data, file_path)

    def _generate_unique_dummy_data(self, pair):
        """종목별 고유한 더미 데이터 생성"""
        import random
        import numpy as np
        from datetime import datetime, timedelta
        
        # 종목코드를 기반으로 한 고정된 랜덤 시드
        random.seed(hash(pair.A_code))
        
        # 기본 가격 범위를 다양하게 설정
        base_price = random.randint(5000, 100000)
        
        # 각 종목별로 다른 변동성 및 트렌드 생성
        trend_direction = 1 if random.random() > 0.5 else -1
        volatility = random.uniform(0.02, 0.1)
        
        dates = []
        common_prices = []
        preferred_prices = []
        discount_rates = []
        sz_values = []
        
        today = datetime.now()
        
        for i in range(365): # 365일로 변경
            date = today - timedelta(days=i)
            dates.append(date.strftime('%Y-%m-%d'))
            
            # 종목별 고유한 가격 변동 생성
            # 사인파 + 랜덤 변동을 통해 더 자연스러운 패턴 생성
            price_variation = (
                trend_direction * 
                np.sin(i/10) * volatility * base_price + 
                random.uniform(-0.02, 0.02) * base_price
            )
            
            common_price = base_price + price_variation
            common_prices.append(int(common_price))
            
            # 괴리율 (-5% ~ 15%)
            discount_rate = random.uniform(-0.05, 0.15)
            discount_rates.append(discount_rate)
            
            # 우선주 가격 (괴리율 적용)
            preferred_price = common_price * (1 - discount_rate)
            preferred_prices.append(int(preferred_price))
            
            # SZ 값 생성 (랜덤 + 패턴)
            sz_value = np.sin(i/20) * 2 + random.uniform(-1, 1)
            sz_values.append(sz_value)
        
        # 신호 생성 로직 추가
        signals = []
        for i in range(1, len(sz_values)):
            if sz_values[i] >= 2.0:
                signals.append({
                    'timestamp': (today - timedelta(days=i)).strftime('%Y-%m-%d %H:%M:%S'),
                    'sz_value': sz_values[i],
                    'signal': 'R__',
                    'price_a': common_prices[i],
                    'price_b': preferred_prices[i]
                })
            elif sz_values[i] >= 1.5 and sz_values[i] < 2.5:
                signals.append({
                    'timestamp': (today - timedelta(days=i)).strftime('%Y-%m-%d %H:%M:%S'),
                    'sz_value': sz_values[i],
                    'signal': '_I_',
                    'price_a': common_prices[i],
                    'price_b': preferred_prices[i]
                })
            elif sz_values[i] < 0.5:
                signals.append({
                    'timestamp': (today - timedelta(days=i)).strftime('%Y-%m-%d %H:%M:%S'),
                    'sz_value': sz_values[i],
                    'signal': '__O',
                    'price_a': common_prices[i],
                    'price_b': preferred_prices[i]
                })
        
        return {
            'stock_code': pair.A_code,
            'stock_name': pair.A_name,
            'dates': dates[::-1], # 최근 날짜가 마지막에 오도록
            'common_prices': common_prices[::-1],
            'preferred_prices': preferred_prices[::-1],
            'discount_rates': discount_rates[::-1],
            'sz_values': sz_values[::-1],
            'signals': signals,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

async def main():
    collector = TrendCollector()
    await collector.collect_all_trends()

if __name__ == "__main__":
    asyncio.run(main())
