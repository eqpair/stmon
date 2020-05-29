# coding=utf8

import requests
import sqlite3
import json
import numpy
from pandas import Series, DataFrame
from bs4 import BeautifulSoup
#from datetime import date, time, datetime, timedelta
import time
import datetime
import telepot
import unicodedata

def preformat_cjk (string, width, align='<', fill=' '):
    count = (width - sum(1 + (unicodedata.east_asian_width(c) in "WF")
                         for c in string))
    return {
        '>': lambda s: fill * count + s,
        '<': lambda s: s + fill * count,
        '^': lambda s: fill * (count / 2)
                       + s
                       + fill * (count / 2 + count % 2)
        }[align](string)

def SendToTelegram(msg) :
    # token : 1112312932:AAGj5iYD9jWQDPYdyh5RKusr8IjRpoLPllE
    # https://api.telegram.org/bot1112312932:AAGj5iYD9jWQDPYdyh5RKusr8IjRpoLPllE/getUpdates
    # myid : 153839694
    token = "1112312932:AAGj5iYD9jWQDPYdyh5RKusr8IjRpoLPllE"
    ji = "153839694"
    bot = telepot.Bot(token)
    #bot.sendMessage(ji, msg)
    #res = bot.sendMessage('@S3PairTN', msg)
    res = bot.sendMessage(-1001234806937, msg)
    #print(res)


class NPPair:
    def __init__(self, code1, code2, sl_in, sl_out, ls_in, ls_out, avg_period):
        self.avg_period = avg_period
        self.A_code = code1
        self.B_code = code2
        self.SL_in_val = sl_in
        self.SL_out_val = sl_out
        self.LS_in_val = ls_in
        self.LS_out_val = ls_out
        
        self.dateList = []
        self.A_closeList = []
        self.B_closeList = []

        self.SL_r = False
        self.LS_r = False
        self.SL_in = False
        self.LS_in = False
        self.SL_out = False
        self.LS_out = False

        self.last_sl_r = False
        self.last_ls_r = False
        self.last_sl_in = False
        self.last_ls_in = False
        self.last_sl_out = False
        self.last_ls_out = False

        yesterday = datetime.date.today() - datetime.timedelta(1)
        
        # A (보통주) 종가 가져오기
        #req = requests.get('https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&count=260&requestType=0'%self.A_code)
        req = requests.get('https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&startTime=%s&count=%d&requestType=0'%(self.A_code, yesterday.strftime('%Y%m%d'), avg_period+20))
        html = req.text
        soup = BeautifulSoup(html, 'html.parser')
        self.A_name = soup.find('chartdata')['name']
        for candle_element in soup.findAll('item'):
            arr = candle_element['data'].split('|')
            self.dateList.append(datetime.date(int(arr[0][0:4]), int(arr[0][4:6]), int(arr[0][6:9])))
            self.A_closeList.append(int(arr[4]))

        # B (우선주) 종가 가져오기
        soup = BeautifulSoup(requests.get('https://fchart.stock.naver.com/sise.nhn?symbol=%s&timeframe=day&startTime=%s&count=%d&requestType=0'%(self.B_code, yesterday.strftime('%Y%m%d'), avg_period+20)).text, 'html.parser')
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
        avg = self.data['dr'].rolling(window=avg_period).mean()
        self.data.insert(len(self.data.columns), 'dr_avg_250', avg)
        # 하루 밀기
        avg = avg.shift(1)

        # 표준편차 구하기
        #std = numpy.std(self.data['dr_avg_250'])
        std = self.data['dr'].rolling(window=avg_period).std()
        self.data.insert(len(self.data.columns), 'std_250', std)
        # 하루 밀기
        std = std.shift(1)

        # 표준화
        sz = []
        for dr,avg,std in zip(self.data['dr'],self.data['dr_avg_250'],self.data['std_250']):
            sz.append( (dr - avg) / std)
        self.data.insert(len(self.data.columns), 'sz_250', sz)

        self.last_avg = self.data.loc[self.data.index[len(self.data.index)-1]][3]
        self.last_std = self.data.loc[self.data.index[len(self.data.index)-1]][4]
        self.last_sz  = self.data.loc[self.data.index[len(self.data.index)-1]][5]
        print('%s vs %s'%(self.A_name, self.B_name))
        print(self.data.tail(10))
        print("LAST avg = %f, std = %f, sz = %f\n"%(self.last_avg, self.last_std, self.last_sz))
        
        self.GetSignalNow(True)

    def GetSignalNow(self, isFirst):
        # 현재가격을 가져온다.
        url = 'https://polling.finance.naver.com/api/realtime.nhn?query=SERVICE_ITEM:%s'%self.A_code
        soup = BeautifulSoup(requests.get(url).text, 'html.parser')
        self.A_price = json.loads(str(soup))['result']['areas'][0]['datas'][0]['nv']
        url = 'https://polling.finance.naver.com/api/realtime.nhn?query=SERVICE_ITEM:%s'%self.B_code
        soup = BeautifulSoup(requests.get(url).text, 'html.parser')
        self.B_price = json.loads(str(soup))['result']['areas'][0]['datas'][0]['nv']

        # 괴리율, 표준화
        dr = (self.A_price - self.B_price)/self.A_price
        sz = (dr - self.last_avg) / self.last_std

        # Signal R
        if (sz > self.SL_in_val): self.SL_r = True
        else: self.SL_r = False
        if (sz < self.LS_in_val): self.LS_r = True
        else: self.LS_r = False
        
        # Short_Long Check
        if (self.last_sz <= self.SL_out_val): self.SL_out = True
        else: self.SL_out = False
        if (self.SL_out):
          self.SL_in = False
        elif(self.SL_in):
          self.SL_in = True
        else: 
          if (self.SL_r and sz < self.last_sz and dr > self.last_avg + (self.last_std * self.SL_in_val)): 
            self.SL_in = True
          else: 
            self.SL_in = False

        # Long_Short Check
        if (self.last_sz >= self.LS_out_val): self.LS_out = True
        else: self.LS_out = False
        if (self.LS_out):
          self.LS_in = False
        elif(self.LS_in):
          self.LS_in = True
        else: 
          if (self.LS_r and sz > self.last_sz and dr < self.last_avg + (self.last_std * self.LS_in_val)): self.LS_in = True
          else: self.LS_in = False

        print("%s : SL %c%c%c | LS %c%c%c | %8d, %8d (%7.3f,%7.3f)"%
            ( preformat_cjk(self.A_name, 10), # self.A_name.ljust(10),
             'R' if self.SL_r else '_', 'I' if self.SL_in else '_', 'O' if self.SL_out else '_',
             'R' if self.LS_r else '_', 'I' if self.LS_in else '_', 'O' if self.LS_out else '_',
             self.A_price, self.B_price, dr, sz))
        
        # 변화 check
        if self.SL_r != self.last_sl_r or \
           self.SL_in != self.last_sl_in or \
           self.SL_out != self.last_sl_out or \
           self.LS_r != self.last_ls_r or \
           self.LS_in != self.last_ls_in or \
           self.LS_out != self.last_ls_out :
            
            msg = ""
            if isFirst:
                # msg = "Start "
                msg = "S "
            else :
                # msg = "Change "
                msg = "C "
#            msg = msg + "(%s)\n  %s : %d, %d (%f,%f) , SL %c%c%c , LS %c%c%c"% \
#                (datetime.datetime.now(), self.A_name, self.A_price, self.B_price, dr, sz, \
#                'R' if self.SL_r else '_', 'I' if self.SL_in else '_', 'O' if self.SL_out else '_', \
#                'R' if self.LS_r else '_', 'I' if self.LS_in else '_', 'O' if self.LS_out else '_')
            msg = msg + " SL %c%c%c , LS %c%c%c %s : %d, %d (%f,%f)"% \
                ('R' if self.SL_r else '_', 'I' if self.SL_in else '_', 'O' if self.SL_out else '_', \
                'R' if self.LS_r else '_', 'I' if self.LS_in else '_', 'O' if self.LS_out else '_', \
                self.A_name, self.A_price, self.B_price, dr, sz)
            print(msg)
            SendToTelegram(msg)
        
        self.last_sl_r = self.SL_r  
        self.last_sl_in = self.SL_in 
        self.last_sl_out = self.SL_out
        self.last_ls_r = self.LS_r  
        self.last_ls_in = self.LS_in 
        self.last_ls_out = self.LS_out
