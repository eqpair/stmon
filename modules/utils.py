from datetime import datetime, time
import logging
import json
import numpy as np
import math  # math.isnan() 및 math.isinf() 함수 사용을 위해 추가
import os 
from config import CODE_TO_NAME

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

def add_weight_info(stock_code, stock_name):
    """
    종목코드와 종목명을 받아서 가중치 정보를 추가한 종목명 반환
    
    Args:
        stock_code (str): 종목 코드
        stock_name (str): 기본 종목명
        
    Returns:
        str: 가중치 정보가 추가된 종목명 (예: '삼성전자 (0.5)')
    """
    # 종목명은 내가 지정한 값만 사용
    display_name = CODE_TO_NAME.get(stock_code, stock_code)
    return display_name

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