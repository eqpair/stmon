from datetime import datetime, time
import logging
import json
import numpy as np

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

class ImprovedNpEncoder(json.JSONEncoder):
    """
    NumPy 데이터 타입을 안전하게 JSON으로 변환하는 인코더
    
    이 클래스는 NumPy의 특수한 데이터 타입(정수, 부동소수점, 배열)을 
    표준 Python 타입으로 변환합니다.
    """
    def default(self, obj):
        # NumPy 정수형 처리
        if isinstance(obj, np.integer):
            return int(obj)
        
        # NumPy 부동소수점 처리
        if isinstance(obj, np.floating):
            # NaN, 무한대 값 처리
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        
        # NumPy 배열 처리
        if isinstance(obj, np.ndarray):
            # NaN 값 제거하고 변환
            return [self.default(x) for x in obj 
                    if not (isinstance(x, float) and np.isnan(x))]
        
        # 기본 JSON 인코더로 처리
        return super(ImprovedNpEncoder, self).default(obj)

def clean_data(data):
    """
    데이터 구조에서 원치 않는 값(NaN, None, 빈 리스트) 제거
    
    이 함수는 재귀적으로 데이터 구조를 탐색하며 다음을 제거합니다:
    - None 값
    - NaN 값
    - 빈 리스트
    
    Args:
        data: 정리할 데이터 (dict, list, 또는 기본 타입)
    
    Returns:
        정리된 데이터
    """
    # 딕셔너리 처리
    if isinstance(data, dict):
        return {
            k: clean_data(v) 
            for k, v in data.items() 
            if v is not None and 
               not (isinstance(v, float) and np.isnan(v)) and 
               not (isinstance(v, list) and len(v) == 0)
        }
    
    # 리스트 처리
    elif isinstance(data, list):
        return [
            clean_data(item) for item in data 
            if item is not None and 
               not (isinstance(item, float) and np.isnan(item)) and 
               not (isinstance(item, list) and len(item) == 0)
        ]
    
    # 부동소수점 NaN 값 처리
    elif isinstance(data, float) and np.isnan(data):
        return None
    
    # 다른 타입은 그대로 반환
    else:
        return data

def safe_json_dump(data, file_path):
    """
    데이터를 안전하게 JSON 파일로 저장
    
    이 함수는 다음 작업을 수행합니다:
    1. 데이터 정리 (clean_data 함수 사용)
    2. 사용자 정의 JSON 인코더로 저장
    3. UTF-8 인코딩 사용
    4. 들여쓰기로 가독성 높임
    
    Args:
        data: JSON으로 저장할 데이터
        file_path: 저장할 파일 경로
    """
    # 데이터 정리
    cleaned_data = clean_data(data)
    
    # JSON으로 저장
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(
            cleaned_data, 
            f, 
            ensure_ascii=False,  # 한글 처리
            indent=2,            # 가독성을 위한 들여쓰기
            cls=ImprovedNpEncoder # 커스텀 인코더 사용
        )