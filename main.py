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
    ('003490', '003495', 2, 1, -2, -1.5),
    ('005930', '005935', 2, 1, -2, -1.5)]

def showSignal(val):
    print(val)

if __name__ == "__main__":
    pairs = []

    for pair in tick_pair:
        np = NPPair(pair[0], pair[1], pair[2], pair[3], pair[4], pair[5], 250)
        pairs.append(np)

    while 1:
        print("> %s"%datetime.datetime.now())
        for np in pairs:
            np.GetSignalNow()
        time.sleep(60)
