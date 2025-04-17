TELEGRAM_TOKEN = "1017606432:AAHQNWYkJDxgQuTHRbYgTkxv-HKtN3Lh9g0"
CHAT_ID = "-1001471005474"

TICK_PAIRS = [
    ('005930', '005935', 2.3, 0.3, -15, -20, 249), #삼성전자
    ('450140', '45014K', 2.0, 0.0, -15, -20, 249), #코오롱모
    ('004100', '004105', 2.2, 0.2, -15, -20, 249), #태양금속
    ('004250', '004255', 2.2, 0.2, -15, -20, 249), #NPC
    ('001790', '001795', 2.3, 0.3, -15, -20, 249), #대한제당
    ('004830', '004835', 2.4, 0.4, -15, -20, 249), #덕성
    ('007810', '007815', 2.3, 0.3, -15, -20, 249), #코리아써
    ('002020', '002025', 2.4, 0.4, -15, -20, 249), #코오롱
    ('005380', '005385', 2.4, 0.4, -15, -20, 249), #현대차
    ('003540', '003545', 2.3, 0.3, -15, -20, 249), #대신증권
    ('004980', '004985', 2.2, 0.2, -15, -20, 249), #성신양회
    ('003070', '003075', 2.3, 0.3, -15, -20, 249), #코오롱글
    ('005940', '005945', 2.2, 0.2, -15, -20, 249), #NH투자
    ('019170', '019175', 2.0, 0.0, -15, -20, 249), #신풍제약
    ('066570', '066575', 2.5, 0.5, -15, -20, 249), #LG전자
    ('009830', '009835', 2.0, 0.0, -15, -20, 249), #한화솔루
    ('004360', '004365', 2.4, 0.4, -15, -20, 249), #세방
    ('003530', '003535', 2.4, 0.4, -15, -20, 249), #한화투자
    ('051900', '051905', 2.4, 0.4, -15, -20, 249), #LG생건
    ('090430', '090435', 2.2, 0.2, -15, -20, 249), #아모레퍼
    ('051910', '051915', 2.4, 0.4, -15, -20, 249), #LG화학
    ('002790', '002795', 2.3, 0.3, -15, -20, 249), #아모레G
    ('003490', '003495', 2.4, 0.4, -15, -20, 249), #대한항공
    ('010950', '010955', 2.6, 0.6, -15, -20, 249), #에스오일
    ('180640', '18064K', 2.1, 0.1, -15, -20, 249), #한진칼
    ('001510', '001515', 2.3, 0.3, -15, -20, 249), #SK증권
    ('071050', '071055', 2.2, 0.2, -15, -20, 249), #한국금융
    ('363280', '36328K', 2.0, 0.0, -15, -20, 249), #티와이
    ('006800', '006805', 2.4, 0.4, -15, -20, 249), #미래에셋
    ('005960', '005965', 2.1, 0.1, -15, -20, 249), #동부건설
    ('264900', '26490K', 2.0, 0.0, -15, -20, 249), #크라운제
    ('000150', '000155', 2.2, 0.2, -15, -20, 249), #두산
    ('008350', '008355', 2.3, 0.3, -15, -20, 249), #남선알미
    ('011780', '011785', 2.4, 0.4, -15, -20, 249), #금호석유
    ('005720', '005725', 2.2, 0.2, -15, -20, 249), #넥센
    ('108670', '108675', 2.3, 0.3, -15, -20, 249), #LX하우
    ('000810', '000815', 2.2, 0.2, -15, -20, 249), #삼성화재
    ('084690', '084695', 2.1, 0.1, -15, -20, 249), #대상홀딩
    ('285130', '28513K', 2.3, 0.3, -15, -20, 249), #SK케미
    ('032680', '032685', 2.0, 0.0, -15, -20, 249), #소프트센
    ('009150', '009155', 2.4, 0.4, -15, -20, 249), #삼성전기
    ('000320', '000325', 2.3, 0.3, -15, -20, 249), #노루홀딩
    ('003550', '003555', 2.2, 0.2, -15, -20, 249), #LG
    ('006400', '006405', 2.1, 0.1, -15, -20, 249), #삼성SDI
    ('120110', '120115', 2.0, 0.0, -15, -20, 249), #코오롱인
    ('006340', '006345', 2.4, 0.4, -15, -20, 249), #대원전선
    ('009410', '009415', 2.3, 0.3, -15, -20, 249), #태영건설
    ('000540', '000545', 2.3, 0.3, -15, -20, 249), #흥국화재
    ('021040', '021045', 2.2, 0.2, -15, -20, 249), #대호특수
    ('012200', '012205', 2.4, 0.4, -15, -20, 249), #계양전기
    ('001750', '001755', 2.1, 0.1, -15, -20, 249), #한양증권
    ('008770', '008775', 2.2, 0.2, -15, -20, 249), #호텔신라
    ('096770', '096775', 2.0, 0.0, -15, -20, 249), #SK이노
    ('004410', '004415', 2.3, 0.3, -15, -20, 249), #서울식품
    ('000720', '000725', 2.2, 0.2, -15, -20, 249), #현대건설
    ('375500', '37550K', 2.0, 0.0, -15, -20, 249), #DL이앤
    ('078930', '078935', 2.1, 0.1, -15, -20, 249), #GS
    ('014280', '014285', 2.2, 0.2, -15, -20, 249), #금강공업
    ('001680', '001685', 2.1, 0.1, -15, -20, 249), #대상
    ('002990', '002995', 2.3, 0.3, -15, -20, 249), #금호건설
    ('097950', '097955', 2.1, 0.1, -15, -20, 249), #CJ제일
    ('006120', '006125', 2.3, 0.3, -15, -20, 249), #SK디스
    ('000210', '000215', 2.2, 0.2, -15, -20, 249), #DL
    ('090350', '090355', 2.3, 0.3, -15, -20, 249), #노루페인
    ('001520', '001525', 2.3, 0.3, -15, -20, 249), #동양
    ('000880', '000885', 2.1, 0.1, -15, -20, 249), #한화
    ('001040', '001045', 2.3, 0.3, -15, -20, 249), #CJ
    ('005740', '005745', 2.0, 0.0, -15, -20, 249), #크라운해
    ('005300', '005305', 2.1, 0.1, -15, -20, 249), #롯데칠성
    ('034730', '03473K', 2.0, 0.0, -15, -20, 249), #SK
    ('014910', '014915', 2.3, 0.3, -15, -20, 249), #성문전자
    ('007570', '007575', 2.5, 0.5, -15, -20, 249), #일양약품
    ('004990', '00499K', 2.0, 0.0, -15, -20, 249), #롯데지주
    ('004540', '004545', 2.3, 0.3, -15, -20, 249), #깨끗한
    ('000100', '000105', 2.2, 0.2, -15, -20, 249), #유한양행
    ('001270', '001275', 2.5, 0.5, -15, -20, 249), #부국증권
    ('003920', '003925', 2.3, 0.3, -15, -20, 249), #남양유업
    ('003460', '003465', 2.3, 0.3, -15, -20, 249), #유화증권
    ('145990', '145995', 2.2, 0.2, -15, -20, 249), #삼양사
    ('001060', '001065', 2.2, 0.2, -15, -20, 249), #JW중외
    ('000140', '000145', 2.3, 0.3, -15, -20, 249), #하이트
    ('001460', '001465', 2.5, 0.5, -15, -20, 249), #BYC
    ('000070', '000075', 2.1, 0.1, -15, -20, 249), #삼양홀딩
    ('014820', '014825', 2.3, 0.3, -15, -20, 249), #동원
]

WAIT_TIME = 600 

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
        '005930': '0.5',  # 삼성전자
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
    }
    
    # 종목 코드에 해당하는 가중치 값이 있으면 종목명에 추가
    if stock_code in weight_map:
        return f"{stock_name} ({weight_map[stock_code]})"
    
    # 가중치 값이 없으면 원래 종목명 반환
    return stock_name