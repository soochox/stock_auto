import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO
from datetime import datetime

# GitHub Secrets에서 환경변수로 불러옴
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

def run_job():
    # 1. 데이터 수집
    base_url = "https://usstocksigma.com/category/expected-move/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # ... (데이터 크롤링 로직은 기존과 동일) ...
    response = requests.get(base_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    latest_post_link = soup.select_one('h2.entry-title a')['href']
    
    post_response = requests.get(latest_post_link, headers=headers)
    tables = pd.read_html(StringIO(post_response.text))
    all_data = pd.concat(tables, ignore_index=True)
    
    # 2. 전처리
    all_data['Ticker'] = all_data['Ticker'].str.upper().str.strip()
    tickers = ['TSLA', 'QQQ', 'AAPL', 'NVDA', 'MSFT'] # 필요시 수정
    result = all_data[all_data['Ticker'].isin(tickers)]
    
    # 3. 텔레그램 전송 (파일도 함께 보내기)
    file_name = f"{datetime.now().strftime('%Y%m%d')}_data.csv"
    result.to_csv(file_name, index=False, encoding='utf-8-sig')
    
    # 텍스트 메시지 전송
    msg = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭*\n\n" + result.to_string(index=False)
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    
    # CSV 파일 전송
    with open(file_name, 'rb') as f:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", data={"chat_id": CHAT_ID}, files={"document": f})

if __name__ == "__main__":
    run_job()
