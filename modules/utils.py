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
        str: 포맷팅된 종목명 (예: '🔴삼성전자 [0.5 @ 2.3]')
    """
    # 종목 코드별 아이콘, 종목명, 가중치, 기준값 매핑
    stock_mapping = {
        '005930': '🔴삼성전자 [0.5 @ 2.3]',
        '450140': '🟢코오롱모빌리티그룹 [4.5 @ 2.0]',
        '004100': '🟢태양금속 [5 @ 2.2]',
        '004250': '⚪NPC [5 @ 2.2]',
        '001790': '⚪대한제당 [5 @ 2.3]',
        '004830': '⚪덕성 [5 @ 2.4]',
        '007810': '⚪코리아써키트 [5 @ 2.3]',
        '002020': '🟢코오롱 [5 @ 2.4]',
        '005380': '🔴현대차 [0.5 @ 2.4]',
        '003540': '⚪대신증권 [5 @ 2.3]',
        '004980': '🟢성신양회 [5 @ 2.2]',
        '003070': '🟢코오롱글로벌 [5 @ 2.3]',
        '005940': '🔵NH투자증권 [1 @ 2.2]',
        '019170': '🟢신풍제약 [1.5 @ 2.0]',
        '066570': '🔵LG전자 [0.5 @ 2.5]',
        '009830': '🟢한화솔루션 [1 @ 2.0]',
        '004360': '⚪세방 [2.5 @ 2.4]',
        '003530': '🟢한화투자증권 [5 @ 2.4]',
        '051900': '🔵LG생활건강 [0.5 @ 2.4]',
        '090430': '⚪아모레퍼시픽 [4.5 @ 2.2]',
        '051910': '🟢LG화학 [0.5 @ 2.4]',
        '002790': '🔵아모레G [0.5 @ 2.3]',
        '003490': '🔵대한항공 [0.04 @ 2.4]',
        '010950': '🔴S-Oil [0.5 @ 2.6]',
        '180640': '🔴한진칼 [1 @ 2.1]',
        '001510': '⚪SK증권 [5 @ 2.3]',
        '071050': '🟠한국금융지주 [1 @ 2.2]',
        '363280': '🟠티와이홀딩스 [5.25 @ 2.0]',
        '006800': '🔵미래에셋증권 [1 @ 2.4]',
        '005960': '⚪동부건설 [5 @ 2.1]',
        '264900': '⚪크라운제과 [5 @ 2.0]',
        '000150': '🟢두산 [0.25 @ 2.2]',
        '008350': '🟢남선알미늄 [5 @ 2.3]',
        '011780': '🔵금호석유 [0.5 @ 2.4]',
        '005720': '⚪넥센 [5 @ 2.2]',
        '108670': '⚪LX하우시스 [5 @ 2.3]',
        '000810': '🟠삼성화재 [0.5 @ 2.2]',
        '084690': '⚪대상홀딩스 [5 @ 2.1]',
        '285130': '🔵SK케미칼 [1 @ 2.3]',
        '032680': '⚪소프트센 [7 @ 2.0]',
        '009150': '🔵삼성전기 [0.5 @ 2.4]',
        '000320': '⚪노루홀딩스 [2 @ 2.3]',
        '003550': '🔵LG [0.5 @ 2.2]',
        '006400': '🔵삼성SDI [0.5 @ 2.1]',
        '120110': '🔵코오롱인더 [1 @ 2.0]',
        '006340': '🟢대원전선 [5 @ 2.4]',
        '009410': '⚪태영건설 [5 @ 2.3]',
        '000540': '⚪흥국화재 [5 @ 2.3]',
        '021040': '🟢대호특수강 [7 @ 2.2]',
        '012200': '⚪계양전기 [5 @ 2.4]',
        '001750': '🟢한양증권 [0.5 @ 2.1]',
        '008770': '🟠호텔신라 [3 @ 2.2]',
        '096770': '🟠SK이노베이션 [1 @ 2.0]',
        '004410': '⚪서울식품 [5 @ 2.3]',
        '000720': '🔵현대건설 [0.5 @ 2.2]',
        '375500': '🔵DL이앤씨 [1 @ 2.0]',
        '078930': '🟠GS [1 @ 2.1]',
        '014280': '⚪금강공업 [5 @ 2.2]',
        '001680': '🔵대상 [1 @ 2.1]',
        '002990': '⚪금호건설 [5 @ 2.3]',
        '097950': '🟠CJ제일제당 [1 @ 2.1]',
        '006120': '🟠SK디스커버리 [5 @ 2.3]',
        '000210': '🔵DL [1 @ 2.2]',
        '090350': '🟢노루페인트 [5 @ 2.3]',
        '001520': '⚪동양 [2.5 @ 2.3]',
        '000880': '⚪한화 [5 @ 2.1]',
        '001040': '🔵CJ [1 @ 2.3]',
        '005740': '🟢크라운해태홀딩스 [5 @ 2.0]',
        '005300': '🟢롯데칠성 [1 @ 2.1]',
        '034730': '🔴SK [0.5 @ 2.0]',
        '014910': '⚪성문전자 [5 @ 2.3]',
        '007570': '🟢일양약품 [5 @ 2.5]',
        '004990': '🟠롯데지주 [1 @ 2.0]',
        '004540': '🟠깨끗한나라 [1.5 @ 2.3]',
        '000100': '🔵유한양행 [1 @ 2.2]',
        '001270': '🟠부국증권 [5 @ 2.5]',
        '003920': '⚪남양유업 [5 @ 2.3]',
        '003460': '⚪유화증권 [5 @ 2.3]',
        '145990': '🟢삼양사 [5 @ 2.2]',
        '001060': '🟢JW중외제약 [5 @ 2.2]',
        '000140': '🟠하이트진로홀딩스 [5 @ 2.3]',
        '001460': '🔵BYC [0.5 @ 2.5]',
        '000070': '🟢삼양홀딩스 [5 @ 2.1]',
        '014820': '⚪동원시스템즈 [5 @ 2.3]'
    }
    
    # 종목 코드에 해당하는 포맷팅된 이름 반환
    if stock_code in stock_mapping:
        return stock_mapping[stock_code]
    
    # 매핑에 없는 경우 기본 이름 반환
    if base_name:
        return f"⚪{base_name} [0 @ 0]"
    
    # 기본 이름도 없는 경우 코드만 반환
    return f"⚪{stock_code} [0 @ 0]"

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