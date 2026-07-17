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
    
    response = requests.get(base_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    latest_post_link = soup.select_one('h2.entry-title a')['href']
    
    post_response = requests.get(latest_post_link, headers=headers)
    tables = pd.read_html(StringIO(post_response.text))
    all_data = pd.concat(tables, ignore_index=True)
    
    # 2. 전처리
    all_data['Ticker'] = all_data['Ticker'].str.upper().str.strip()
    tickers = ['QQQ', 'SOXX', 'TSLA', 'PLTR', 'MSFT'] # 필요시 수정
    filtered_df = all_data[all_data['Ticker'].isin(tickers)].copy()
    
    if not filtered_df.empty:
        # --- [2시그마 계산 및 데이터 추가] ---
        cols = filtered_df.columns
        price_col = next((c for c in cols if any(x in c.lower() for x in ['price', 'current', 'underlying', '주가', '현재가'])), None)
        em_col = next((c for c in cols if 'expected move' in c.lower() and '%' not in c.lower() and '2' not in c.lower() and '시그마' not in c.lower()), None)
        
        # 숫자만 안전하게 추출하는 함수
        def clean_float(val):
            if pd.isna(val): return 0.0
            cleaned = "".join(c for c in str(val) if c.isdigit() or c == '.' or c == '-')
            try: return float(cleaned)
            except: return 0.0

        if price_col and em_col:
            prices = filtered_df[price_col].apply(clean_float)
            em_1s = filtered_df[em_col].apply(clean_float)
            
            # 1시그마 범위 자동 추가
            has_1s_range = any('1-sigma' in c.lower() or '1 sigma' in c.lower() or '1시그마' in c.lower() for c in cols)
            if not has_1s_range:
                filtered_df['Range (1-Sigma)'] = [f"${(p - em):.2f} ~${(p + em):.2f}" if p > 0 and em > 0 else "N/A" for p, em in zip(prices, em_1s)]
            
            # 2시그마 변동폭 및 범위 자동 추가
            has_2s_move = any('2-sigma' in c.lower() or '2 sigma' in c.lower() or '2시그마' in c.lower() for c in cols)
            if not has_2s_move:
                filtered_df['Expected Move (2-Sigma)'] = em_1s.apply(lambda x: f"±${x*2:.2f}" if x > 0 else "N/A")
                filtered_df['Range (2-Sigma)'] = [f"${(p - em*2):.2f} ~${(p + em*2):.2f}" if p > 0 and em > 0 else "N/A" for p, em in zip(prices, em_1s)]
        
        # --- [텔레그램 모바일용 표 정렬 최적화] ---
        r1_col = next((c for c in filtered_df.columns if '1-sigma' in c.lower() or '1 sigma' in c.lower() or '1시그마' in c.lower() or 'range' in c.lower() and '2' not in c.lower()), None)
        r2_col = next((c for c in filtered_df.columns if '2-sigma' in c.lower() or '2 sigma' in c.lower() or '2시그마' in c.lower()), None)
        
        if price_col and r1_col and r2_col:
            # 스마트폰 화면에 맞게 헤더 글자수 축소
            table_lines = [f"{'Ticker':<7} {'Price':<8} {'1-Sigma':<16} {'2-Sigma':<16}"]
            table_lines.append("-" * 50)
            for _, row in filtered_df.iterrows():
                ticker = str(row.get('Ticker', ''))[:6]
                price = str(row.get(price_col, ''))[:7]
                # 공백과 달러 기호 제거로 너비 최소화
                r1 = str(row.get(r1_col, 'N/A')).replace('$', '').replace(' ', '')
                r2 = str(row.get(r2_col, 'N/A')).replace('$', '').replace(' ', '')
                table_lines.append(f"{ticker:<7} {price:<8} {r1:<16} {r2:<16}")
            
            formatted_table = "\n".join(table_lines)
        else:
            # 예외 상황 시 기존 방식 사용
            formatted_table = filtered_df.to_string(index=False)

        # 백틱(```)으로 감싸서 고정폭 폰트 적용
        msg = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭 (1 & 2시그마)*\n\n" + "```\n" + formatted_table + "\n```"
        
        # 3. 텍스트 메시지만 텔레그램 전송
        requests.post(f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_job()
