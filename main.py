import requests
from bs4 import BeautifulSoup
from datetime import date, time, datetime

# dataSet = ["005930": [ '20200213', 61200, 61600, 60500, 60700, 18449775]]
#req = requests.get('https://beomi.github.io/beomi.github.io_old/')
req = requests.get(
    'https://fchart.stock.naver.com/sise.nhn?symbol=005930&timeframe=day&count=10&requestType=0')

html = req.text
#xml = req.text

soup = BeautifulSoup(html, 'html.parser')
#soup = BeautifulSoup(xml, 'xml')
#data = soup.select('item > data')
#data = soup.select('h3 > a')

for candle_element in soup.findAll('item'):
    print(candle_element['data'])
    arr = candle_element['data'].split('|')
    nalja = date(int(arr[0][0:4]), int(arr[0][4:6]), int(arr[0][6:9]))
    o = int(arr[1])
    h = int(arr[2])
    l = int(arr[3])
    c = int(arr[4])

    print("%s, %d, %d, %d, %d" % (nalja, o, h, l, c))
