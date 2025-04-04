#!/usr/bin/env python3

import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup

from config import TICK_PAIRS
from modules.pairs import NPPair

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
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
        
    async def collect_all_trends(self):
        """모든 종목의 트렌드 데이터 수집"""
        logger.info("트렌드 데이터 수집 시작...")
        
        tasks = []
        for pair in self.pairs:
            task = asyncio.create_task(self.collect_trend_data(pair))
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count
        
        logger.info(f"트렌드 데이터 수집 완료: 성공 {success_count}개, 실패 {error_count}개")
    
    async def collect_trend_data(self, pair):
        """특정 종목 페어의 트렌드 데이터 수집"""
        try:
            # 세션 가져오기
            session = await self._get_session()
            
            # 1년(365일) 데이터 가져오기로 수정
            days_to_fetch = 365
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_to_fetch)
            
            # A 종목(보통주) 데이터 가져오기
            a_data = await self._fetch_stock_history(session, pair.A_code, start_date, days_to_fetch+30)
            
            # B 종목(우선주) 데이터 가져오기
            b_data = await self._fetch_stock_history(session, pair.B_code, start_date, days_to_fetch+30)
            
            # 데이터 처리 및 저장
            result = self._process_trend_data(pair, a_data, b_data)
            if result:
                self._save_trend_data(pair.A_code, result)
                logger.info(f"{pair.A_name} 트렌드 데이터 수집 완료 (1년치)")
                return True
            else:
                logger.warning(f"{pair.A_name} 트렌드 데이터 처리 실패")
                return False
        
        except Exception as e:
            logger.error(f"{pair.A_name} 트렌드 데이터 수집 중 오류: {str(e)}")
            raise
    
    async def _fetch_stock_history(self, session, stock_code, start_date, days):
        """주식 히스토리 데이터 가져오기 - 1년 데이터용 수정"""
        # 네이버 금융 API URL (일별 차트 데이터)
        # 1년치 데이터를 위해 충분한 수의 데이터 요청
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={stock_code}&timeframe=day&startTime={start_date.strftime('%Y%m%d')}&count={days}&requestType=0"
        
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"API 응답 오류 ({stock_code}): HTTP {response.status}")
                    return None
                
                return await response.text()
        
        except Exception as e:
            logger.error(f"데이터 요청 중 오류 ({stock_code}): {str(e)}")
            return None
    
    def _process_trend_data(self, pair, a_data, b_data):
    try:
        # 데이터 파싱 시 추가 로깅
        logger.info(f"Processing data for {pair.A_name}")
        logger.info(f"A_code: {pair.A_code}, B_code: {pair.B_code}")
        logger.info(f"Pair parameters: SL_in_val={pair.SL_in_val}, avg_period={pair.avg_period}")

        # 데이터 파싱
        a_df = self._parse_stock_data(a_data, pair.A_code)
        b_df = self._parse_stock_data(b_data, pair.B_code)
        
        if a_df is None or b_df is None or a_df.empty or b_df.empty:
            logger.warning(f"{pair.A_name} 데이터 파싱 실패")
            return None
        
        # 데이터 병합
        merged_df = pd.merge(a_df, b_df, left_index=True, right_index=True, suffixes=('_A', '_B'))
        
        # 로깅: 병합된 데이터 정보
        logger.info(f"Merged data length: {len(merged_df)}")
        logger.info(f"Date range: {merged_df.index[0]} to {merged_df.index[-1]}")

        # 괴리율 계산 
        merged_df['dr'] = (merged_df['close_A'] - merged_df['close_B']) / merged_df['close_A']
        
        # 추가 로깅: 괴리율 통계
        logger.info(f"Discount rate - Mean: {merged_df['dr'].mean()}, Std: {merged_df['dr'].std()}")
        
        # 이동평균 (1일 shift)
        merged_df['dr_avg'] = merged_df['dr'].rolling(window=pair.avg_period).mean().shift(1)
        
        # 표준편차 (1일 shift)
        merged_df['std'] = merged_df['dr'].rolling(window=pair.avg_period).std().shift(1)
        
        # SZ 값 계산
        merged_df['sz'] = (merged_df['dr'] - merged_df['dr_avg']) / merged_df['std']
        
        # SZ 값 로깅 (최근 10개 데이터)
        logger.info("Recent SZ values:")
        logger.info(merged_df['sz'].tail(10).to_string())

        # 전체 데이터를 사용하되 최소 365일 데이터 보장
        all_data = merged_df.sort_index()
        recent_data = all_data.tail(max(365, len(all_data)))
        
        # 신호 생성 로직
        signals = self._generate_signals(recent_data, pair)
        
        # 신호 로깅
        logger.info("Generated Signals:")
        for signal in signals[:10]:  # 최대 10개 신호 로깅
            logger.info(str(signal))
        
        # 결과 포맷팅
        result = {
            'stock_code': pair.A_code,
            'stock_name': pair.A_name,
            'dates': recent_data.index.strftime('%Y-%m-%d').tolist(),
            'common_prices': recent_data['close_A'].tolist(),
            'preferred_prices': recent_data['close_B'].tolist(),
            'discount_rates': recent_data['dr'].tolist(),
            'sz_values': recent_data['sz'].tolist(),
            'signals': signals,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return result
        
    except Exception as e:
        logger.error(f"{pair.A_name} 트렌드 데이터 처리 중 오류: {str(e)}")
        # 전체 스택 트레이스 로깅
        import traceback
        logger.error(traceback.format_exc())
        return None

    def _generate_signals(self, data, pair):
    signals = []
    
    # 로깅 추가
    logger.info(f"Generating signals for {pair.A_name}")
    logger.info(f"Data length: {len(data)}")
    logger.info(f"SL_in_val: {pair.SL_in_val}, SL_out_val: {pair.SL_out_val}")
    
    for i in range(1, len(data)):
        last_row = data.iloc[i]
        prev_row = data.iloc[i-1]
        
        sz = last_row['sz']
        T = (sz * 10) + 50

        signal_conditions = {
            'SL_R': sz > pair.SL_in_val,
            'LS_R': sz < pair.LS_in_val,
            'SL_O': sz <= pair.SL_out_val,
            'LS_O': sz >= pair.LS_out_val,
            'SL_I': (sz > pair.SL_in_val and 
                    T > 70 and 
                    sz < prev_row['sz'] and 
                    last_row['dr'] > last_row['dr_avg'] + (last_row['std'] * pair.SL_in_val)),
            'LS_I': (sz < pair.LS_in_val and 
                    T < 30 and 
                    sz > prev_row['sz'] and 
                    last_row['dr'] < last_row['dr_avg'] + (last_row['std'] * pair.LS_in_val))
        }
        
        # 각 조건에 대한 상세 로깅
        if logger.getEffectiveLevel() == logging.DEBUG:
            for condition, value in signal_conditions.items():
                logger.debug(f"{condition}: {value}")
        
        if any(signal_conditions.values()):
            signal_info = f"{'R' if signal_conditions['SL_R'] else '_'}"
            signal_info += f"{'I' if signal_conditions['SL_I'] else '_'}"
            signal_info += f"{'O' if signal_conditions['SL_O'] else '_'}"
            
            signal_entry = {
                'timestamp': last_row.name.strftime('%Y-%m-%d %H:%M:%S'),
                'sz_value': sz,
                'signal': signal_info,
                'price_a': last_row['close_A'],
                'price_b': last_row['close_B']
            }
            
            # 신호 생성 시 상세 로깅
            logger.info(f"Signal generated: {signal_entry}")
            signals.append(signal_entry)
    
    logger.info(f"Total signals generated: {len(signals)}")
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
                if len(data) >= 5:  # 데이터가 충분한지 확인
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
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
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
        
        for i in range(365):  # 365일로 변경
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
            'dates': dates[::-1],  # 최근 날짜가 마지막에 오도록
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