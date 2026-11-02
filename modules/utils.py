from datetime import datetime, time
import logging
import json
import numpy as np
import math  # math.isnan() 및 math.isinf() 함수 사용을 위해 추가
import os 

logger = logging.getLogger(__name__)

def is_market_time() -> bool:
    """
    현재 시간이 주식 시장 운영 시간인지 확인하는 함수
    
    Returns:
        bool: 주식 시장 운영 시간이면 True, 아니면 False
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    # 평일 (월요일~금요일)
    is_weekday = 0 <= weekday <= 4
    
    # 주식 시장 운영 시간 (오전 8시 30분 ~ 오후 4시 30분)
    is_work_hours = time(8, 30) <= current_time <= time(16, 30)
    
    return is_weekday and is_work_hours

def format_stock_name(stock_code, base_name=None):
    """
    종목코드를 받아 [아이콘 + 종목명 + 가중치/기준값] 형태로 포맷팅된 문자열 반환
    
    Args:
        stock_code (str): 종목 코드
        base_name (str, optional): 기본 종목명, 없으면 매핑에서 찾음
        
    Returns:
        str: 포맷팅된 종목명 (예: '🔴삼성전자')
    """
    # 종목 코드별 아이콘, 종목명, 가중치, 기준값 매핑
    stock_mapping = {
        '005930': '🔴 삼성전자',
        '450140': '🔵 코오롱모빌리티그룹(비)',
        '004100': '🟢 태양금속(비)',
        '004250': '🔵 NPC(비)',
        '001790': '🔵 대한제당(비)',
        '004830': '🟠 덕성(비)',
        '007810': '🔵 코리아써키트(비)',
        '002020': '🟠 코오롱(비)',
        '005380': '🔴 현대차',
        '003540': '⚪ 대신증권(비)',
        '004980': '🟢 성신양회(비)',
        '003070': '🟢 코오롱글로벌(비)',
        '005940': '🔵 NH투자증권',
        '019170': '🟢 신풍제약(비)',
        '066570': '⚪ LG전자',
        '009830': '🟢 한화솔루션',
        '004360': '🟠 세방(비)',
        '003530': '🔵 한화투자증권(비)',
        '051900': '⚪ LG생활건강',
        '090430': '🔵 아모레퍼시픽',
        '051910': '🟠 LG화학',
        '002790': '🔵 아모레G',
        '003490': '🔵 대한항공',
        '010950': '🟠 S-Oil',
        '180640': '🔴 한진칼',
        '001510': '🟢 SK증권(비)',
        '071050': '🔵 한국금융지주',
        '363280': '⚪ 티와이홀딩스(비)',
        '006800': '🔵 미래에셋증권',
        '005960': '🔵 동부건설(비)',
        '264900': '🔵 크라운제과(비)',
        '000150': '🟢 두산',
        '008350': '🟢 남선알미늄(비)',
        '011780': '🔵 금호석유',
        '005720': '🔵 넥센(비)',
        '108670': '🔵 LX하우시스(비)',
        '000810': '🔴 삼성화재',
        '084690': '🔵 대상홀딩스(비)',
        '285130': '🔵 SK케미칼',
        '032680': '🔵 소프트센(비)',
        '009150': '⚪ 삼성전기',
        '000320': '🔵 노루홀딩스(비)',
        '003550': '🔵 LG',
        '006400': '🔵 삼성SDI',
        '120110': '🔵 코오롱인더',
        '006340': '🟢 대원전선(비)',
        '009410': '🔵 태영건설(비)',
        '000540': '🔵 흥국화재(비)',
        '021040': '🟢 대호특수강(비)',
        '012200': '🔵 계양전기(비)',
        '001750': '🟢 한양증권(비)',
        '008770': '🔴 호텔신라',
        '096770': '🔴 SK이노베이션',
        '004410': '🔴 서울식품(비)',
        '000720': '🟠 현대건설',
        '375500': '🔴 DL이앤씨',
        '078930': '🔵 GS',
        '014280': '🔵 금강공업(비)',
        '001680': '⚪ 대상',
        '002990': '🔵 금호건설(비)',
        '097950': '🟠 CJ제일제당',
        '006120': '🟠 SK디스커버리(비)',
        '000210': '🔵 DL',
        '090350': '🟢 노루페인트(비)',
        '001520': '🔵 동양(비)',
        '000880': '🔴 한화',
        '001040': '🟠 CJ',
        '005740': '🟢 크라운해태홀딩스(비)',
        '005300': '🟢 롯데칠성',
        '034730': '🟠 SK',
        '014910': '🔵 성문전자(비)',
        '007570': '🟢 일양약품(비)',
        '004990': '🔵 롯데지주',
        '004540': '🔵 깨끗한나라(비)',
        '000100': '🔵 유한양행',
        '001270': '🟠 부국증권(비)',
        '003920': '🟠 남양유업(비)',
        '003460': '🔵 유화증권(비)',
        '145990': '⚪ 삼양사(비)',
        '001060': '🟢 JW중외제약(비)',
        '000140': '🟠 하이트진로홀딩스(비)',
        '001460': '🟠 BYC(비)',
        '000070': '🟢 삼양홀딩스(비)',
        '014820': '🔵 동원시스템즈',
        '042670': '⚪ HD현대인프라_건설'
    }
    
    # 종목 코드에 해당하는 포맷팅된 이름 반환
    if stock_code in stock_mapping:
        return stock_mapping[stock_code]
    
    # 매핑에 없는 경우 기본 이름 반환
    if base_name:
        return f"⚪ {base_name}"
    
    # 기본 이름도 없는 경우 코드만 반환
    return f"⚪ {stock_code}"

# 기존 함수 호환성 유지를 위한 래퍼 함수
def add_weight_info(stock_code, stock_name):
    """
    기존 add_weight_info 함수와의 호환성을 위한 래퍼 함수
    """
    return format_stock_name(stock_code, stock_name)
 

class ImprovedNpEncoder(json.JSONEncoder):
    def default(self, obj):
        # NumPy 정수형 처리
        if isinstance(obj, np.integer):
            return int(obj)
        
        # NumPy 부동소수점 처리
        if isinstance(obj, np.floating):
            # NaN, 무한대 값 처리 - 명시적으로 None으로 변환
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        
        # NumPy 배열 처리
        if isinstance(obj, np.ndarray):
            # NaN 값을 None으로 변환하여 배열 반환
            return [None if (isinstance(x, (float, np.floating)) and (np.isnan(x) or np.isinf(x))) 
                   else self.default(x) for x in obj]
        
        # 일반 float 타입의 NaN, Infinity 값도 처리
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
            
        # 기본 JSON 인코더로 처리
        return super(ImprovedNpEncoder, self).default(obj)

def clean_data(data):
    """
    데이터 구조에서 원치 않는 값(NaN, None, 빈 리스트) 제거
    """
    # 딕셔너리 처리
    if isinstance(data, dict):
        return {
            k: clean_data(v) 
            for k, v in data.items() 
            if v is not None and 
               not (isinstance(v, (float, np.float64)) and (np.isnan(v) or np.isinf(v))) and 
               not (isinstance(v, list) and len(v) == 0)
        }
    
    # 리스트 처리
    elif isinstance(data, list):
        return [
            clean_data(item) for item in data 
            if item is not None and 
               not (isinstance(item, (float, np.float64)) and (np.isnan(item) or np.isinf(item))) and 
               not (isinstance(item, list) and len(item) == 0)
        ]
    
    # 부동소수점 NaN, Infinity 값 처리
    elif isinstance(data, (float, np.float64)) and (np.isnan(data) or np.isinf(data)):
        return None
    
    # 다른 타입은 그대로 반환
    else:
        return data

# utils.py의 safe_json_dump 함수 수정
# modules/utils.py 파일에 추가/수정
def safe_json_dump(data, file_path):
    """데이터를 안전하게 JSON 파일로 저장"""
    import json
    import numpy as np
    import os

    try:
        # 데이터 정리 - NaN, 무한대 값 처리
        def clean_value(v):
            if isinstance(v, (float, np.floating)) and (np.isnan(v) or np.isinf(v)):
                return None
            elif isinstance(v, dict):
                return {k: clean_value(val) for k, val in v.items()}
            elif isinstance(v, list):
                return [clean_value(item) for item in v]
            return v
        
        # 데이터 정리
        cleaned_data = clean_value(data)
        
        # 디렉토리 확인 및 생성
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        
        # 임시 파일에 먼저 저장
        temp_file = f"{file_path}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2, 
                     default=lambda o: None if isinstance(o, (float, np.floating)) and (np.isnan(o) or np.isinf(o)) else o)
            f.flush()
            os.fsync(f.fileno())  # 디스크에 확실히 쓰기
        
        # 원자적으로 파일 교체
        os.replace(temp_file, file_path)
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"JSON 저장 오류 ({file_path}): {str(e)}")
        # 임시 파일 정리
        try:
            if os.path.exists(f"{file_path}.tmp"):
                os.remove(f"{file_path}.tmp")
        except:
            pass
        
        # 기본 방식으로 저장 시도 (폴백)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json_str = json.dumps(data, ensure_ascii=False, indent=2, 
                                     default=lambda o: None if isinstance(o, (float, np.floating)) and (np.isnan(o) or np.isinf(o)) else o)
                json_str = json_str.replace('"NaN"', 'null').replace('NaN', 'null')
                f.write(json_str)
            return True
        except Exception as backup_err:
            logging.getLogger(__name__).error(f"기본 JSON 저장도 실패 ({file_path}): {str(backup_err)}")
            return False