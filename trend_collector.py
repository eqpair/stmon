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
        """트렌드 데이터 처리 - 1년치 데이터 처리로 수정"""
        if not a_data or not b_data:
            return None
        
        try:
            # 데이터 파싱
            a_df = self._parse_stock_data(a_data, pair.A_code)
            b_df = self._parse_stock_data(b_data, pair.B_code)
            
            if a_df is None or b_df is None or a_df.empty or b_df.empty:
                logger.warning(f"{pair.A_name} 데이터 파싱 실패")
                return None
            
            # 두 데이터프레임 병합
            merged_df = pd.merge(a_df, b_df, left_index=True, right_index=True, suffixes=('_A', '_B'))
            
            # 괴리율 계산
            merged_df['discount_rate'] = (merged_df['close_A'] - merged_df['close_B']) / merged_df['close_A']
            
            # 전체 데이터를 사용하되 최소 365일 데이터 보장하기
            # 최근 데이터부터 최대 365일까지 저장
            all_data = merged_df.sort_index()
            recent_data = all_data.tail(max(365, len(all_data)))
            
            # 결과 포맷팅
            result = {
                'stock_code': pair.A_code,
                'stock_name': pair.A_name,
                'dates': recent_data.index.strftime('%Y-%m-%d').tolist(),
                'common_prices': recent_data['close_A'].tolist(),
                'preferred_prices': recent_data['close_B'].tolist(),
                'discount_rates': recent_data['discount_rate'].tolist(),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return result
            
        except Exception as e:
            logger.error(f"{pair.A_name} 트렌드 데이터 처리 중 오류: {str(e)}")
            return None
    
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

async def main():
    collector = TrendCollector()
    await collector.collect_all_trends()

if __name__ == "__main__":
    asyncio.run(main())