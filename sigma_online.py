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
    site_domain = "usstocksigma.com"
    base_url = "https://" + site_domain + "/category/expected-move/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(base_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    latest_post_link = soup.select_one('h2.entry-title a')['href']
    
    post_response = requests.get(latest_post_link, headers=headers)
    tables = pd.read_html(StringIO(post_response.text))
    all_data = pd.concat(tables, ignore_index=True)
    
    # 전처리
    all_data.columns = [str(c).strip() for c in all_data.columns]
    all_data['Ticker'] = all_data['Ticker'].astype(str).str.upper().str.strip()
    tickers = ['QQQ', 'SOXX', 'TSLA', 'PLTR', 'MSFT'] 
    filtered_df = all_data[all_data['Ticker'].isin(tickers)].copy()
    
    if not filtered_df.empty:
        # 데이터 추출 (계산을 위해 열 위치 확인)
        price_col = next((c for c in filtered_df.columns if any(x in str(c).lower() for x in ['price', 'current', '주가', '현재가'])), filtered_df.columns[1])
        em_col = next((c for c in filtered_df.columns if any(x in str(c).lower() for x in ['move', '변동폭']) and '%' not in str(c).lower()), filtered_df.columns[2])
        
        def clean_float(val):
            if pd.isna(val): return 0.0
            cleaned = "".join(c for c in str(val) if c.isdigit() or c == '.' or c == '-')
            try: return float(cleaned)
            except: return 0.0

        prices = filtered_df[price_col].apply(clean_float)
        em_1s = filtered_df[em_col].apply(clean_float)
        
        # 텔레그램 API 설정
        api_domain = "api.telegram.org"
        telegram_url = "https://" + api_domain + "/bot" + str(TOKEN) + "/sendMessage"

        # --------------------------------------------------
        # 메시지 1: 1시그마 원본 (filtered_df를 그대로 전송)
        # --------------------------------------------------
        msg_1s = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭 (1시그마 - 원본)*\n\n" + "```\n" + filtered_df.to_string(index=False) + "\n```"
        requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg_1s, "parse_mode": "Markdown"})

        # --------------------------------------------------
        # 메시지 2: 2시그마 계산값만 전송
        # --------------------------------------------------
        table_lines_2s = [f"{'Ticker':<7} {'2-Sigma Range':<20}"]
        table_lines_2s.append("-" * 28)
        
        # 계산만 따로 수행
        for _, row in filtered_df.iterrows():
            ticker = str(row['Ticker'])[:6]
            p = clean_float(row[price_col])
            em = clean_float(row[em_col])
            
            # 2시그마 범위 계산
            range_2s = f"${(p - em*2):.2f} ~ ${(p + em*2):.2f}" if p > 0 and em > 0 else "N/A"
            table_lines_2s.append(f"{ticker:<7} {range_2s:<20}")
            
        msg_2s = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 2시그마 계산값*\n\n" + "```\n" + "\n".join(table_lines_2s) + "\n```"
        requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg_2s, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_job()
