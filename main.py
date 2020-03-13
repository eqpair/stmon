# 초 간단 버전

# DR : disparate ratio
# STD : standard deviation
# SZ : standardization
# An close | Ap close | disparate ratio | DR AVG 250 | STD 250 | SZ | signal in | signal out

import requests
import sqlite3
import json
import numpy
from pandas import Series, DataFrame
from bs4 import BeautifulSoup
#from datetime import date, time, datetime, timedelta
import time
import datetime

class NPPair:
    def __init__(self, code1, code2):
        self.A_code = code1
        self.B_code = code2
        self.SL_in_val = 2
        self.SL_out_val = 1
        self.LS_in_val = -2
        self.LS_out_val = -1.5
        
        self.dateList = []
        self.A_closeList = []
        self.B_closeList = []

        yesterday = datetime.date.today() - datetime.timedelta(1)
        
        # A (보통주) 종가 가져오기
        #req = requests.get('https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&count=260&requestType=0'%self.A_code)
        req = requests.get('https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&startTime=%s&count=260&requestType=0'%(self.A_code, yesterday.strftime('%Y%m%d')))
        html = req.text
        soup = BeautifulSoup(html, 'html.parser')
        self.A_name = soup.find('chartdata')['name']
        for candle_element in soup.findAll('item'):
            arr = candle_element['data'].split('|')
            self.dateList.append(datetime.date(int(arr[0][0:4]), int(arr[0][4:6]), int(arr[0][6:9])))
            self.A_closeList.append(int(arr[4]))

        # B (우선주) 종가 가져오기
        soup = BeautifulSoup(requests.get('https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&startTime=%s&count=260&requestType=0'%(self.B_code, yesterday.strftime('%Y%m%d'))).text, 'html.parser')
        self.B_name = soup.find('chartdata')['name']
        for candle_element in soup.findAll('item'):
            self.B_closeList.append(int(candle_element['data'].split('|')[4]))

        # DataFrame 생성
        self.data = DataFrame(
            { 'a_close': self.A_closeList,
              'b_close': self.B_closeList},
            columns=['a_close','b_close'],
            index=self.dateList
        )

        # 괴리율 구하기
        disparateRatio = []
        for a_val,b_val in zip(self.A_closeList,self.B_closeList):
            disparateRatio.append( (a_val - b_val)/a_val)
        self.data.insert(len(self.data.columns), 'dr', disparateRatio)

        # 괴리율 평균 구하기
        avg = self.data['dr'].rolling(window=250).mean()
        self.data.insert(len(self.data.columns), 'dr_avg_250', avg)

        # 표준편차 구하기
        #std = numpy.std(self.data['dr_avg_250'])
        std = self.data['dr'].rolling(window=250).std()
        self.data.insert(len(self.data.columns), 'std_250', std)

        # 표준화
        sz = []
        for dr,avg,std in zip(self.data['dr'],self.data['dr_avg_250'],self.data['std_250']):
            sz.append( (dr - avg) / std)
        self.data.insert(len(self.data.columns), 'sz_250', sz)

        #self.last_avg = 
        print('%s vs %s'%(self.A_name, self.B_name))
        #print(self.data)
        print(self.data.tail(30))
        

    def GetSignalNow(self):
        # 현재가격을 가져온다.
        url = 'https://polling.finance.naver.com/api/realtime.nhn?query=SERVICE_ITEM:%s'%self.A_code
        soup = BeautifulSoup(requests.get(url).text, 'html.parser')
        self.A_price = json.loads(str(soup))['result']['areas'][0]['datas'][0]['nv']
        url = 'https://polling.finance.naver.com/api/realtime.nhn?query=SERVICE_ITEM:%s'%self.B_code
        soup = BeautifulSoup(requests.get(url).text, 'html.parser')
        self.B_price = json.loads(str(soup))['result']['areas'][0]['datas'][0]['nv']

        # 괴리율
        dr = (self.A_price - self.B_price)/self.A_price

        print("Current Price : %d, %d (%f)"%(self.A_price, self.B_price, dr))

        # signal 처리



if __name__ == "__main__":
    #pair1 = NPPair('005930', '005935')
    # TODO: 종목을 설정으로 받자.
    pair1 = NPPair('003490', '003495')

    while 1:
        pair1.GetSignalNow()

        time.sleep(60)
