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

def add_weight_info(stock_code, stock_name):
    """
    종목코드와 종목명을 받아서 가중치 정보를 추가한 종목명 반환
    
    Args:
        stock_code (str): 종목 코드
        stock_name (str): 기본 종목명
        
    Returns:
        str: 가중치 정보가 추가된 종목명 (예: '삼성전자 (0.5)')
    """
    # 종목 코드 별 가중치 값 매핑
    weight_map = {
        '005930': '0.5 [2.3]',  # 삼성전자
        '450140': '4.5',  # 코오롱모빌리티그룹
        '004100': '5',    # 태양금속
        '004250': '5',    # NPC
        '001790': '5',    # 대한제당
        '004830': '5',    # 덕성
        '007810': '5',    # 코리아써키트
        '002020': '5',    # 코오롱
        '005380': '0.5',  # 현대차
        '003540': '5',    # 대신증권
        '004980': '5',    # 성신양회
        '003070': '5',    # 코오롱글로벌
        '005940': '1',    # NH투자증권
        '019170': '1.5',  # 신풍제약
        '066570': '0.5',  # LG전자
        '009830': '1',    # 한화솔루션
        '004360': '2.5',  # 세방
        '003530': '5',    # 한화투자증권
        '051900': '0.5',  # LG생활건강
        '090430': '4.5',  # 아모레퍼시픽
        '051910': '0.5',  # LG화학
        '002790': '0.5',  # 아모레G
        '003490': '0.04', # 대한항공
        '010950': '0.5',  # S-Oil
        '180640': '1',    # 한진칼
        '001510': '5',    # SK증권
        '071050': '1',    # 한국금융지주
        '363280': '5.25', # 티와이홀딩스
        '006800': '1',    # 미래에셋증권
        '005960': '5',    # 동부건설
        '264900': '5',    # 크라운제과
        '000150': '0.25', # 두산
        '008350': '5',    # 남선알미늄
        '011780': '0.5',  # 금호석유
        '005720': '5',    # 넥센
        '108670': '5',    # LX하우시스
        '000810': '0.5',  # 삼성화재
        '084690': '5',    # 대상홀딩스
        '285130': '1',    # SK케미칼
        '032680': '7',    # 소프트센
        '009150': '0.5',  # 삼성전기
        '000320': '2',    # 노루홀딩스
        '003550': '0.5',  # LG
        '006400': '0.5',  # 삼성SDI
        '120110': '1',    # 코오롱인더
        '006340': '5',    # 대원전선
        '009410': '5',    # 태영건설
        '000540': '5',    # 흥국화재
        '021040': '7',    # 대호특수강
        '012200': '5',    # 계양전기
        '001750': '0.5',  # 한양증권
        '008770': '3',    # 호텔신라
        '096770': '1',    # SK이노베이션
        '004410': '5',    # 서울식품
        '000720': '0.5',  # 현대건설
        '375500': '1',    # DL이앤씨
        '078930': '1',    # GS
        '014280': '5',    # 금강공업
        '001680': '1',    # 대상
        '002990': '5',    # 금호건설
        '097950': '1',    # CJ제일제당
        '006120': '5',    # SK디스커버리
        '000210': '1',    # DL
        '090350': '5',    # 노루페인트
        '001520': '2.5',  # 동양
        '000880': '5',    # 한화
        '001040': '1',    # CJ
        '005740': '5',    # 크라운해태홀딩스
        '005300': '1',    # 롯데칠성
        '034730': '0.5',  # SK
        '014910': '5',    # 성문전자
        '007570': '5',    # 일양약품
        '004990': '1',    # 롯데지주
        '004540': '1.5',  # 깨끗한나라
        '000100': '1',    # 유한양행
        '001270': '5',    # 부국증권
        '003920': '5',    # 남양유업
        '003460': '5',    # 유화증권
        '145990': '5',    # 삼양사
        '001060': '5',    # JW중외제약
        '000140': '5',    # 하이트진로홀딩스
        '001460': '0.5',  # BYC
        '000070': '5',    # 삼양홀딩스
        '014820': '5'     # 동원시스템즈즈
    }
    
    # 종목 코드에 해당하는 가중치 값이 있으면 종목명에 추가
    if stock_code in weight_map:
        return f"{stock_name} ({weight_map[stock_code]})"
    
    # 가중치 값이 없으면 원래 종목명 반환
    return stock_name

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