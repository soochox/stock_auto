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
    
    # 컬럼명 안전하게 처리 (한글/영문 호환)
    all_data.columns = [str(c).strip() for c in all_data.columns]
    ticker_col = next((c for c in all_data.columns if any(x in c.lower() for x in ['ticker', '티커', '종목'])), all_data.columns[0])
    
    # 2. 전처리
    all_data[ticker_col] = all_data[ticker_col].astype(str).str.upper().str.strip()
    tickers = ['QQQ', 'SOXX', 'TSLA', 'PLTR', 'MSFT'] # 필요시 수정
    filtered_df = all_data[all_data[ticker_col].isin(tickers)].copy()
    
    if not filtered_df.empty:
        cols = filtered_df.columns
        price_col = next((c for c in cols if any(x in c.lower() for x in ['price', 'current', 'underlying', '주가', '현재가'])), None)
        em_col = next((c for c in cols if any(x in c.lower() for x in ['expected move', '변동폭']) and '%' not in c.lower() and '2' not in c.lower() and '시그마' not in c.lower()), None)
        
        # 🌟 회원님의 원본 로직 (숫자 꼬임 방지 100% 복구) 🌟
        def clean_float(val):
            if pd.isna(val): return 0.0
            cleaned = "".join(c for c in str(val) if c.isdigit() or c == '.' or c == '-')
            try: return float(cleaned)
            except: return 0.0

        if price_col and em_col:
            prices = filtered_df[price_col].apply(clean_float)
            em_1s = filtered_df[em_col].apply(clean_float)
            
            # 1시그마 및 2시그마 범위 계산
            filtered_df['Range_1S'] = [f"${(p - em):.2f} ~ ${(p + em):.2f}" if p > 0 and em > 0 else "N/A" for p, em in zip(prices, em_1s)]
            filtered_df['Range_2S'] = [f"${(p - em*2):.2f} ~ ${(p + em*2):.2f}" if p > 0 and em > 0 else "N/A" for p, em in zip(prices, em_1s)]
            
            # --- [텔레그램 모바일용 표 1: 1시그마] ---
            table_lines_1s = [f"{'Ticker':<7} {'Price':<8} {'1-Sigma':<16}"]
            table_lines_1s.append("-" * 33)
            for _, row in filtered_df.iterrows():
                ticker = str(row.get(ticker_col, ''))[:6]
                price = str(row.get(price_col, ''))[:7]
                r1 = str(row['Range_1S']).replace('$', '').replace(' ', '')
                table_lines_1s.append(f"{ticker:<7} {price:<8} {r1:<16}")
            
            formatted_table_1s = "\n".join(table_lines_1s)
            
            # --- [텔레그램 모바일용 표 2: 2시그마] ---
            table_lines_2s = [f"{'Ticker':<7} {'Price':<8} {'2-Sigma':<16}"]
            table_lines_2s.append("-" * 33)
            for _, row in filtered_df.iterrows():
                ticker = str(row.get(ticker_col, ''))[:6]
                price = str(row.get(price_col, ''))[:7]
                r2 = str(row['Range_2S']).replace('$', '').replace(' ', '')
                table_lines_2s.append(f"{ticker:<7} {price:<8} {r2:<16}")
            
            formatted_table_2s = "\n".join(table_lines_2s)
            
        else:
            # 예외 상황 시 원본 출력
            formatted_table_1s = filtered_df.to_string(index=False)
            formatted_table_2s = "데이터 추출 오류"

        # 3. 텔레그램 전송 (메시지 2개 분할)
        api_domain = "api.telegram.org"
        telegram_url = "https://" + api_domain + "/bot" + str(TOKEN) + "/sendMessage"

        # [첫 번째 메시지] 1시그마 전송
        msg_1s = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭 (1시그마)*\n\n" + "```\n" + formatted_table_1s + "\n```"
        requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg_1s, "parse_mode": "Markdown"})

        # [두 번째 메시지] 2시그마 전송
        msg_2s = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭 (2시그마)*\n\n" + "```\n" + formatted_table_2s + "\n```"
        requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg_2s, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_job()
