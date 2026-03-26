import aiohttp
import pandas as pd
import numpy as np
from typing import Tuple, Optional
from datetime import datetime, timedelta
import logging
from bs4 import BeautifulSoup
import json
import asyncio
from modules.exceptions import MarketDataError
from .utils import add_weight_info
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
        self.skew_long = 0.0
        self.skew_short = 0.0
        self._last_fetch_date = None  # 마지막 전체 fetch 날짜 캐시

    async def fetch_data(self):
        """과거 데이터 전체 fetch - 하루 1회만 실행"""
        try:
            async with aiohttp.ClientSession() as session:
                a_data = await self._fetch_stock_data(session, self.A_code)
                b_data = await self._fetch_stock_data(session, self.B_code)
                self._process_data(a_data, b_data)
            self._last_fetch_date = datetime.now().date()
        except Exception as e:
            logger.error(f"Error fetching data: {str(e)}")
            raise MarketDataError(f"Failed to fetch market data: {str(e)}")

    async def fetch_current_price_and_update(self):
        """현재가만 fetch해서 마지막 행 업데이트 - 매 주기 실행"""
        try:
            async with aiohttp.ClientSession() as session:
                a_price = await self._fetch_current_price(session, self.A_code)
                b_price = await self._fetch_current_price(session, self.B_code)

            if a_price is None or b_price is None:
                logger.warning(f"현재가 fetch 실패, 캐시 데이터 사용: {self.A_name}")
                return

            if self.data.empty:
                logger.warning(f"캐시 데이터 없음, 전체 fetch 필요: {self.A_name}")
                await self.fetch_data()
                return

            today = pd.Timestamp(datetime.now().date())

            # 오늘 날짜 행이 이미 있으면 현재가로 업데이트, 없으면 새 행 추가
            if today in self.data.index:
                self.data.at[today, 'close_A'] = a_price
                self.data.at[today, 'close_B'] = b_price
            else:
                new_row = pd.DataFrame(
                    {'close_A': [a_price], 'close_B': [b_price]},
                    index=[today]
                )
                self.data = pd.concat([self.data, new_row])

            self._calculate_metrics()

        except Exception as e:
            logger.error(f"현재가 업데이트 오류 ({self.A_name}): {str(e)}")

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
        try:
            a_df = self._parse_stock_data(a_data, self.A_code)
            b_df = self._parse_stock_data(b_data, self.B_code)
            
            if a_df is None or b_df is None or a_df.empty or b_df.empty:
                logger.error(f"데이터 프레임 생성 실패: a_df={a_df is not None}, b_df={b_df is not None}")
                self.data = pd.DataFrame()
                return
                
            self.data = pd.merge(a_df, b_df, left_index=True, right_index=True, suffixes=('_A', '_B'))
            self._calculate_metrics()
            self.A_name = a_df.name
            self.B_name = b_df.name
        except Exception as e:
            logger.error(f"데이터 처리 중 오류: {str(e)}")
            self.data = pd.DataFrame()

    def _parse_stock_data(self, data: str, code: str) -> pd.DataFrame:
        try:
            soup = BeautifulSoup(data, features="html.parser")
            chartdata = soup.find('chartdata')
            
            if chartdata is None:
                raise MarketDataError(f"Failed to parse data for {code}: No chartdata found")
                
            from .utils import format_stock_name
            name = format_stock_name(code)
            
            items = soup.find_all('item')
            if not items:
                raise MarketDataError(f"Failed to parse data for {code}: No items found")
            
            dates = []
            closes = []
            
            for item in items:
                if 'data' not in item.attrs:
                    continue
                    
                data = item['data'].split('|')
                if len(data) >= 5:
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
        
        self.skew_long = round(self.data['dr'].skew(), 2)
        self.skew_short = round(self.data['dr'].tail(60).skew(), 2)

    async def get_signal_now(self) -> Optional[str]:
        today = datetime.now().date()

        # 오늘 전체 fetch를 아직 안 했거나 데이터가 비어있으면 전체 fetch
        if self._last_fetch_date != today or self.data.empty:
            await self.fetch_data()
        else:
            # 현재가만 가볍게 업데이트
            await self.fetch_current_price_and_update()

        return self._generate_signal()

    def _generate_signal(self) -> Optional[str]:
        if self.data is None or self.data.empty:
            logger.error(f"No data available for signal generation: {self.A_code} vs {self.B_code}")
            return None
        try:
            last_row = self.data.iloc[-1]
            sz = last_row['sz']

            if sz >= self.SL_in_val:
                signal = "IN"
            elif sz <= self.SL_out_val:
                signal = "OUT"
            else:
                signal = "CHK"

            price_info = f"{last_row['close_A']:.0f}, {last_row['close_B']:.0f}"
            ratio_info = f"{sz:.2f}"
            skew_info = f"SKW {'+' if self.skew_long >= 0 else ''}{self.skew_long}/{'+' if self.skew_short >= 0 else ''}{self.skew_short}"
            return f"{ratio_info} / {signal} / {price_info} / {skew_info}"

        except Exception as e:
            logger.error(f"Error generating signal: {str(e)}")
            raise

    async def get_current_prices(self) -> Tuple[float, float]:
        """현재 주가를 가져오는 함수 - 개선된 버전으로 여러 번 재시도"""
        max_retries = 3
        backoff_time = 1
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    a_price = await self._fetch_current_price(session, self.A_code)
                    b_price = await self._fetch_current_price(session, self.B_code)
                    
                    if a_price is not None and b_price is not None:
                        logger.info(f"현재 가격 성공적으로 가져옴: {self.A_name}({self.A_code}): {a_price}, {self.B_code}: {b_price}")
                        return a_price, b_price
                    
                    logger.warning(f"현재 가격 데이터가 없음, 재시도 {attempt+1}/{max_retries}: {self.A_name}")
                    
            except Exception as e:
                logger.error(f"현재 가격 가져오기 오류, 재시도 {attempt+1}/{max_retries}: {self.A_name} - {str(e)}")
                
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_time)
                backoff_time *= 2
        
        try:
            return await self._get_fallback_prices()
        except Exception as fallback_error:
            logger.error(f"가격 폴백 조회 실패: {self.A_name} - {str(fallback_error)}")
            return None, None
        
    async def _get_fallback_prices(self) -> Tuple[float, float]:
        """API 호출 실패 시 데이터 폴백 - 저장된 데이터에서 최신 가격 가져오기"""
        try:
            from pathlib import Path
            import os
            
            data_dir = Path(f"{os.environ.get('GITHUB_REPO_PATH', '/home/pi/work/m5000')}/data")
            trends_dir = data_dir / "trends"
            trend_file = trends_dir / f"{self.A_code}.json"
            
            if not os.path.exists(trend_file):
                logger.warning(f"트렌드 파일 없음: {trend_file}")
                raise FileNotFoundError(f"트렌드 파일 없음: {trend_file}")
                
            with open(trend_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if data and 'common_prices' in data and 'preferred_prices' in data:
                common_prices = data['common_prices']
                preferred_prices = data['preferred_prices']
                
                if common_prices and preferred_prices:
                    last_common = common_prices[-1]
                    last_preferred = preferred_prices[-1]
                    
                    if last_common is not None and last_preferred is not None:
                        logger.info(f"폴백 가격 사용: {self.A_name} - 보통주:{last_common}, 우선주:{last_preferred}")
                        return float(last_common), float(last_preferred)
            
            logger.warning(f"폴백 데이터 없음: {self.A_name}")
            raise ValueError(f"폴백 데이터 없음: {self.A_name}")
            
        except Exception as e:
            logger.error(f"폴백 가격 가져오기 오류: {self.A_name} - {str(e)}")
            raise

    async def _fetch_current_price(self, session: aiohttp.ClientSession, code: str) -> float:
        """현재 주가를 API에서 가져오는 함수"""
        url = f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}'
        try:
            async with session.get(url, timeout=5) as response:
                if response.status != 200:
                    logger.warning(f"가격 API 응답 오류 ({code}): HTTP {response.status}")
                    return None
                    
                data = await response.text()
                
                try:
                    json_data = json.loads(data)
                    
                    if not json_data or 'result' not in json_data or 'areas' not in json_data['result']:
                        logger.warning(f"API 응답 형식 오류 ({code}): {data[:100]}...")
                        return None
                        
                    areas = json_data['result']['areas']
                    if not areas or not areas[0].get('datas'):
                        logger.warning(f"API 응답에 데이터 없음 ({code})")
                        return None
                        
                    price = areas[0]['datas'][0].get('nv')
                    
                    if price is None or (isinstance(price, str) and not price.isdigit()):
                        logger.warning(f"유효하지 않은 가격 ({code}): {price}")
                        return None
                        
                    return float(price)
                    
                except json.JSONDecodeError as json_err:
                    logger.error(f"JSON 파싱 오류 ({code}): {str(json_err)}")
                    return None
                except Exception as parse_err:
                    logger.error(f"가격 데이터 처리 오류 ({code}): {str(parse_err)}")
                    return None
                    
        except aiohttp.ClientError as http_err:
            logger.error(f"HTTP 요청 오류 ({code}): {str(http_err)}")
            return None
        except asyncio.TimeoutError:
            logger.error(f"가격 요청 타임아웃 ({code})")
            return None
        except Exception as e:
            logger.error(f"가격 요청 중 예상치 못한 오류 ({code}): {str(e)}")
            return None