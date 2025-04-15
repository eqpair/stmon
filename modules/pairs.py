import aiohttp
import pandas as pd
import numpy as np
from typing import Tuple, Optional
from datetime import datetime, timedelta
import logging
from bs4 import BeautifulSoup
import json
from .exceptions import MarketDataError
from .utils import add_weight_info  # add_weight_info 함수 임포트 추가
from bs4 import XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)

class NPPair:
    def __init__(self, code1: str, code2: str, sl_in: float, sl_out: float,
                 ls_in: float, ls_out: float, avg_period: int):
        self.A_code = code1
        self.B_code = code2
        self.SL_in_val = sl_in
        self.SL_out_val = sl_out
        self.LS_in_val = ls_in
        self.LS_out_val = ls_out
        self.avg_period = avg_period
        self.data = pd.DataFrame()
        self.A_name = ""
        self.B_name = ""
        self.T = 50
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch_data(self):
        session = None
        try:
            session = await self._get_session()
            async with session:
                a_data = await self._fetch_stock_data(session, self.A_code)
                b_data = await self._fetch_stock_data(session, self.B_code)
            self._process_data(a_data, b_data)
        except Exception as e:
            logger.error(f"Error fetching data: {str(e)}")
            raise MarketDataError(f"Failed to fetch market data: {str(e)}")
        finally:
            # 세션이 닫히지 않았다면 명시적으로 닫기
            if session and not session.closed:
                await session.close()

    async def _fetch_stock_data(self, session: aiohttp.ClientSession, code: str) -> str:
        yesterday = datetime.now() - timedelta(1)
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&startTime={yesterday.strftime('%Y%m%d')}&count={self.avg_period+120}&requestType=0"
        
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    raise MarketDataError(f"HTTP {response.status} for {code}")
                return await response.text()
        except Exception as e:
            logger.error(f"Error fetching {code}: {str(e)}")
            raise

    def _process_data(self, a_data: str, b_data: str):
        a_df = self._parse_stock_data(a_data, self.A_code)
        b_df = self._parse_stock_data(b_data, self.B_code)
        self.data = pd.merge(a_df, b_df, left_index=True, right_index=True, suffixes=('_A', '_B'))
        self._calculate_metrics()
        self.A_name = a_df.name
        self.B_name = b_df.name

    def _parse_stock_data(self, data: str, code: str) -> pd.DataFrame:
        try:
            soup = BeautifulSoup(data, features="html.parser")
            chartdata = soup.find('chartdata')
            
            if chartdata is None:
                raise MarketDataError(f"Failed to parse data for {code}: No chartdata found")
                
            # chartdata에서 name 속성을 찾고, 없으면 code를 사용
            name = chartdata.get('name', code)
            
            # 종목명에 가중치 정보 추가
            name = add_weight_info(code, name)
            
            # item들을 찾습니다
            items = soup.find_all('item')
            if not items:
                raise MarketDataError(f"Failed to parse data for {code}: No items found")
            
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
                        logger.warning(f"Skipping malformed data in {code}: {str(e)}")
                        continue
            
            if not dates or not closes:
                raise MarketDataError(f"No valid data parsed for {code}")
                
            df = pd.DataFrame({'close': closes}, index=dates)
            df.name = name
            return df
            
        except Exception as e:
            logger.error(f"Error parsing stock data for {code}: {str(e)}")
            raise MarketDataError(f"Failed to parse stock data for {code}: {str(e)}")

    def _calculate_metrics(self):
        self.data['dr'] = (self.data['close_A'] - self.data['close_B']) / self.data['close_A']
        self.data['dr_avg'] = self.data['dr'].rolling(window=self.avg_period).mean().shift(1)
        self.data['std'] = self.data['dr'].rolling(window=self.avg_period).std().shift(1)
        self.data['sz'] = (self.data['dr'] - self.data['dr_avg']) / self.data['std']

    async def get_signal_now(self) -> Optional[str]:
        await self.fetch_data()
        return self._generate_signal()

    def _generate_signal(self) -> Optional[str]:
        try:
            last_row = self.data.iloc[-1]
            prev_row = self.data.iloc[-2]
            
            sz = last_row['sz']
            self.T = (sz * 10) + 50

            signal_conditions = {
                'SL_R': sz > self.SL_in_val,
                'LS_R': sz < self.LS_in_val,
                'SL_O': sz <= self.SL_out_val,
                'LS_O': sz >= self.LS_out_val,
                'SL_I': (sz > self.SL_in_val and 
                        self.T > 70 and 
                        sz < prev_row['sz'] and 
                        last_row['dr'] > last_row['dr_avg'] + (last_row['std'] * self.SL_in_val)),
                'LS_I': (sz < self.LS_in_val and 
                        self.T < 30 and 
                        sz > prev_row['sz'] and 
                        last_row['dr'] < last_row['dr_avg'] + (last_row['std'] * self.LS_in_val))
            }
            
            # 이 부분을 수정: 신호 생성 방식 통일
            signal_parts = []
            if signal_conditions['SL_R'] or signal_conditions['LS_R']:
                signal_parts.append('R')
            if signal_conditions['SL_I'] or signal_conditions['LS_I']:
                signal_parts.append('I')
            if signal_conditions['SL_O'] or signal_conditions['LS_O']:
                signal_parts.append('O')
                
            signal_info = ''.join(signal_parts)
            price_info = f"{last_row['close_A']:.0f}, {last_row['close_B']:.0f}"
            ratio_info = f"{sz:.2f}"
            
            # 포맷 수정: sz/신호/가격 형식으로 통일
            if signal_info:
                return f"{ratio_info} / {signal_info} / {price_info}"
            
            # 신호가 없더라도 SZ 값만 반환
            return f"{ratio_info} / / {price_info}"
            
        except Exception as e:
            logger.error(f"Error generating signal: {str(e)}")
            raise

    async def get_current_prices(self) -> Tuple[float, float]:
        session = await self._get_session()
        async with session:
            a_price = await self._fetch_current_price(session, self.A_code)
            b_price = await self._fetch_current_price(session, self.B_code)
        return a_price, b_price

    async def _fetch_current_price(self, session: aiohttp.ClientSession, code: str) -> float:
        url = f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}'
        async with session.get(url) as response:
            data = await response.text()
        json_data = json.loads(data)
        return json_data['result']['areas'][0]['datas'][0]['nv']