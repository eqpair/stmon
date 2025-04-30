import aiohttp
import pandas as pd
import numpy as np
from typing import Tuple, Optional
from datetime import datetime, timedelta
import logging
from bs4 import BeautifulSoup
import json
import asyncio  # asyncio.sleep에 필요
from modules.exceptions import MarketDataError
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
        try:
            a_df = self._parse_stock_data(a_data, self.A_code)
            b_df = self._parse_stock_data(b_data, self.B_code)
            
            # None 또는 빈 DataFrame 확인 및 처리
            if a_df is None or b_df is None or a_df.empty or b_df.empty:
                logger.error(f"데이터 프레임 생성 실패: a_df={a_df is not None}, b_df={b_df is not None}")
                self.data = pd.DataFrame()  # 빈 데이터 프레임 설정
                return
                
            self.data = pd.merge(a_df, b_df, left_index=True, right_index=True, suffixes=('_A', '_B'))
            self._calculate_metrics()
            self.A_name = a_df.name
            self.B_name = b_df.name
        except Exception as e:
            logger.error(f"데이터 처리 중 오류: {str(e)}")
            self.data = pd.DataFrame()  # 오류 발생 시 빈 데이터 프레임으로 설정

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
        """현재 주가를 가져오는 함수 - 개선된 버전으로 여러 번 재시도"""
        max_retries = 3
        backoff_time = 1  # 초 단위로 대기 시간
        
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                async with session:
                    a_price = await self._fetch_current_price(session, self.A_code)
                    b_price = await self._fetch_current_price(session, self.B_code)
                    
                    # 가격 데이터가 유효한지 확인
                    if a_price is not None and b_price is not None:
                        logger.info(f"현재 가격 성공적으로 가져옴: {self.A_name}({self.A_code}): {a_price}, {self.B_code}: {b_price}")
                        return a_price, b_price
                    
                    logger.warning(f"현재 가격 데이터가 없음, 재시도 {attempt+1}/{max_retries}: {self.A_name}")
                    
            except Exception as e:
                logger.error(f"현재 가격 가져오기 오류, 재시도 {attempt+1}/{max_retries}: {self.A_name} - {str(e)}")
                
            # 마지막 시도가 아니면 대기 후 재시도
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_time)
                backoff_time *= 2  # 지수 백오프
        
        # 모든 재시도 실패 시, 저장된 데이터 반환 시도
        try:
            return await self._get_fallback_prices()
        except Exception as fallback_error:
            logger.error(f"가격 폴백 조회 실패: {self.A_name} - {str(fallback_error)}")
            # 데이터가 없는 경우 기본값 반환 - 0 대신 None을 반환하면 호출자가 알아서 처리 가능
            return None, None
        
    async def _get_fallback_prices(self) -> Tuple[float, float]:
        """API 호출 실패 시 데이터 폴백 - 저장된 데이터에서 최신 가격 가져오기"""
        try:
            from pathlib import Path
            import json
            import os
            
            # 트렌드 파일 경로
            data_dir = Path(f"{os.environ.get('GITHUB_REPO_PATH', '/home/pi/work/m5000')}/data")
            trends_dir = data_dir / "trends"
            trend_file = trends_dir / f"{self.A_code}.json"
            
            # 파일이 존재하는지 확인
            if not os.path.exists(trend_file):
                logger.warning(f"트렌드 파일 없음: {trend_file}")
                raise FileNotFoundError(f"트렌드 파일 없음: {trend_file}")
                
            # 파일 데이터 읽기
            with open(trend_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 최신 가격 가져오기
            if data and 'common_prices' in data and 'preferred_prices' in data:
                common_prices = data['common_prices']
                preferred_prices = data['preferred_prices']
                
                if common_prices and preferred_prices:
                    # 마지막 값 가져오기
                    last_common = common_prices[-1]
                    last_preferred = preferred_prices[-1]
                    
                    if last_common is not None and last_preferred is not None:
                        logger.info(f"폴백 가격 사용: {self.A_name} - 보통주:{last_common}, 우선주:{last_preferred}")
                        return float(last_common), float(last_preferred)
            
            # 데이터가 없으면 예외 발생
            logger.warning(f"폴백 데이터 없음: {self.A_name}")
            raise ValueError(f"폴백 데이터 없음: {self.A_name}")
            
        except Exception as e:
            logger.error(f"폴백 가격 가져오기 오류: {self.A_name} - {str(e)}")
            raise

    async def _fetch_current_price(self, session: aiohttp.ClientSession, code: str) -> float:
        """현재 주가를 API에서 가져오는 함수 - 오류 처리 강화"""
        url = f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}'
        try:
            async with session.get(url, timeout=5) as response:
                if response.status != 200:
                    logger.warning(f"가격 API 응답 오류 ({code}): HTTP {response.status}")
                    return None
                    
                data = await response.text()
                
                # JSON 파싱
                try:
                    json_data = json.loads(data)
                    
                    # 데이터 구조 확인
                    if not json_data or 'result' not in json_data or 'areas' not in json_data['result']:
                        logger.warning(f"API 응답 형식 오류 ({code}): {data[:100]}...")
                        return None
                        
                    areas = json_data['result']['areas']
                    if not areas or not areas[0].get('datas'):
                        logger.warning(f"API 응답에 데이터 없음 ({code})")
                        return None
                        
                    # 가격 추출
                    price = areas[0]['datas'][0].get('nv')
                    
                    # 가격이 숫자인지 확인
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