import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO
from datetime import datetime
import re

# GitHub Secrets에서 환경변수로 불러옴
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

def run_job():
    # 1. 데이터 수집 (자동 링크 변환 방지 처리)
    site_domain = "usstocksigma.com"
    base_url = "https://" + site_domain + "/category/expected-move/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(base_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    latest_post_link = soup.select_one('h2.entry-title a')['href']
    
    post_response = requests.get(latest_post_link, headers=headers)
    tables = pd.read_html(StringIO(post_response.text))
    all_data = pd.concat(tables, ignore_index=True)
    
    # 컬럼명 앞뒤 공백 제거
    all_data.columns = [str(c).strip() for c in all_data.columns]
    
    # 2. 전처리 및 필터링
    ticker_col = next((c for c in all_data.columns if any(x in c.lower() for x in ['ticker', '티커', '종목'])), all_data.columns[0])
    all_data[ticker_col] = all_data[ticker_col].astype(str).str.upper().str.strip()
    
    tickers = ['QQQ', 'SOXX', 'TSLA', 'PLTR', 'MSFT'] # 필요시 수정
    filtered_df = all_data[all_data[ticker_col].isin(tickers)].copy()
    
    if not filtered_df.empty:
        cols = filtered_df.columns
        
        # 주가 및 변동폭 컬럼 찾기
        price_col = next((c for c in cols if any(x in c.lower() for x in ['price', 'current', 'underlying', '주가', '현재가', '종가'])), None)
        if not price_col and len(cols) > 1: price_col = cols[1]
            
        em_col = next((c for c in cols if any(x in c.lower() for x in ['move', '변동폭']) and not any(y in c.lower() for y in ['%', '2', '시그마', 'sigma'])), None)
        if not em_col and len(cols) > 2: em_col = cols[2]
        
        # 숫자 추출 함수
        def clean_float(val):
            if pd.isna(val): return 0.0
            match = re.search(r'[-+]?\d*\.\d+|\d+', str(val))
            if match:
                try: return float(match.group())
                except: return 0.0
            return 0.0

        if price_col and em_col:
            prices = filtered_df[price_col].apply(clean_float)
            em_1s = filtered_df[em_col].apply(clean_float)
            
            # 1시그마 범위 확인 및 생성
            r1_col = next((c for c in cols if any(x in c.lower() for x in ['1-sigma', '1 sigma', '1시그마', '범위', 'range']) and '2' not in c.lower()), None)
            if not r1_col:
                filtered_df['1-Sigma Range'] = [f"${(p - em):.2f} ~ ${(p + em):.2f}" if p > 0 and em > 0 else "N/A" for p, em in zip(prices, em_1s)]
                r1_col = '1-Sigma Range'
            
            # 2시그마 데이터 자동 계산 및 생성
            filtered_df['2-Sigma Move'] = em_1s.apply(lambda x: f"±${x*2:.2f}" if x > 0 else "N/A")
            filtered_df['2-Sigma Range'] = [f"${(p - em*2):.2f} ~ ${(p + em*2):.2f}" if p > 0 and em > 0 else "N/A" for p, em in zip(prices, em_1s)]
            
            # 텔레그램 API 주소 세팅
            api_domain = "api.telegram.org"
            telegram_url = "https://" + api_domain + "/bot" + str(TOKEN) + "/sendMessage"

            # --------------------------------------------------
            # 메시지 1: 1시그마 알림 전송 (정렬용 컬럼 정리)
            # --------------------------------------------------
            df_1s = filtered_df[[ticker_col, price_col, em_col, r1_col]].copy()
            df_1s.columns = ['Ticker', 'Price', '1-Sigma', '1-Sigma Range']
            
            formatted_table_1s = df_1s.to_string(index=False)
            msg_1s = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭 (1시그마 - 68.3%)*\n\n" + "```\n" + formatted_table_1s + "\n```"
            
            requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg_1s, "parse_mode": "Markdown"})

            # --------------------------------------------------
            # 메시지 2: 2시그마 알림 전송 (정렬용 컬럼 정리)
            # --------------------------------------------------
            df_2s = filtered_df[[ticker_col, price_col, '2-Sigma Move', '2-Sigma Range']].copy()
            df_2s.columns = ['Ticker', 'Price', '2-Sigma', '2-Sigma Range']
            
            formatted_table_2s = df_2s.to_string(index=False)
            msg_2s = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭 (2시그마 - 95.4%)*\n\n" + "```\n" + formatted_table_2s + "\n```"
            
            requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg_2s, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_job()
