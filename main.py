# 초 간단 버전

# DR : disparate ratio
# STD : standard deviation
# SZ : standardization
# An close | Ap close | disparate ratio | DR AVG 250 | STD 250 | SZ | signal in | signal out

import time
import datetime
from NPPair import NPPair

# 보통주, 우선주, SL_IN, SL_OUT, LS_IN, LS_OUT
tick_pair = [
    ('003490', '003495', 2, 1, -2, -1.5),   # 대한항공
    ('005930', '005935', 2, 1, -2, -1.5),   # 삼성전자
    ('003920', '003925', 2, 1, -2, -1.5),   # 남양유업
    ('000210', '000215', 2, 1, -2, -1.5),   # 대림산업
    ('011780', '011785', 2, 1, -2, -1.5),   # 금호석유
    ('005380', '005385', 2, 1, -2, -1.5),   # 현대차
    ('000810', '000815', 2, 1, -2, -1.5),   # 삼성화재
    ('006400', '006405', 2, 1, -2, -1.5),   # 삼성SDI
    ('009150', '009155', 2, 1, -2, -1.5),   # 삼성전기
    ('008770', '008775', 2, 1, -2, -1.5),   # 호텔신라
    ('019170', '019175', 2, 1, -2, -1.5),   # 신풍제약
    ('051900', '051905', 2, 1, -2, -1.5),   # LG생활건강
    ('180640', '18064K', 2, 1, -2, -1.5),   # 한진칼
    ]

def showSignal(val):
    print(val)

if __name__ == "__main__":
    pairs = []

    for pair in tick_pair:
        np = NPPair(pair[0], pair[1], pair[2], pair[3], pair[4], pair[5], 250)
        pairs.append(np)

    while 1:
        time.sleep(60)
        print("> %s"%datetime.datetime.now())
        for np in pairs:
            np.GetSignalNow(False)
        
