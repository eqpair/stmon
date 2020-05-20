# 초 간단 버전

# DR : disparate ratio
# STD : standard deviation
# SZ : standardization
# An close | Ap close | disparate ratio | DR AVG 250 | STD 250 | SZ | signal in | signal out

import time
import datetime
from NPPair import NPPair

def showSignal(val):
    print(val)

if __name__ == "__main__":
    #pair1 = NPPair('005930', '005935')
    # TODO: 종목을 설정으로 받자.
    pair1 = NPPair('003490', '003495', 250)

    while 1:
        pair1.GetSignalNow()

        time.sleep(60)
