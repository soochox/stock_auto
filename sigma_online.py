import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO
from datetime import datetime
import re  # 숫자 추출을 위한 정규식 라이브러리 추가

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
    
    # 컬럼명 앞뒤 공백 제거 및 확실하게 문자열 처리
    all_data.columns = [str(c).strip() for c in all_data.columns]
    
    # 2. 전처리 및 필터링
    # 티커 컬럼 매칭 (없으면 첫 번째 컬럼 사용)
    ticker_col = next((c for c in all_data.columns if any(x in c.lower() for x in ['ticker', '티커', '종목'])), all_data.columns[0])
    
    all_data[ticker_col] = all_data[ticker_col].astype(str).str.upper().str.strip()
    tickers = ['QQQ', 'SOXX', 'TSLA', 'PLTR', 'MSFT'] # 필요시 수정
    filtered_df = all_data[all_data[ticker_col].isin(tickers)].copy()
    
    if not filtered_df.empty:
        cols = filtered_df.columns
        
        # [현재가 컬럼 매칭] 한글/영어 모두 지원 (없으면 2번째 컬럼 사용)
        price_col = next((c for c in cols if any(x in c.lower() for x in ['price', 'current', 'underlying', '주가', '현재가', '종가'])), None)
        if not price_col and len(cols) > 1:
            price_col = cols[1]
            
        # [1시그마 변동폭 컬럼 매칭] 한글/영어 모두 지원 (없으면 3번째 컬럼 사용)
        em_col = next((c for c in cols if any(x in c.lower() for x in ['move', '변동폭']) and not any(y in c.lower() for y in ['%', '2', '시그마', 'sigma'])), None)
        if not em_col and len(cols) > 2:
            em_col = cols[2]
        
        # 특수기호나 괄호가 섞여 있어도 숫자만 안전하게 추출하는 함수
        def clean_float(val):
            if pd.isna(val): return 0.0
            match = re.search(r'[-+]?\d*\.\d+|\d+', str(val))
            if match:
                try: return float(match.group())
                except: return 0.0
            return 0.0

        # 2시그마 계산 작동
        if price_col and em_col:
            prices = filtered_df[price_col].apply(clean_float)
            em_1s = filtered_df[em_col].apply(clean_float)
            
            # 2시그마 변동폭 및 범위 자동 계산 후 추가
            has_2s_move = any(any(x in c.lower() for x in ['2-sigma', '2 sigma', '2시그마']) for c in cols)
            if not has_2s_move:
                filtered_df['Expected Move (2-Sigma)'] = em_1s.apply(lambda x: f"±${x*2:.2f}" if x > 0 else "N/A")
                filtered_df['Range (2-Sigma)'] = [f"${(p - em*2):.2f} ~${(p + em*2):.2f}" if p > 0 and em > 0 else "N/A" for p, em in zip(prices, em_1s)]
        
        # --- [텔레그램 모바일용 표 정렬 최적화] ---
        # 1시그마 범위 컬럼 매칭 (없으면 5번째 컬럼 사용)
        r1_col = next((c for c in filtered_df.columns if any(x in c.lower() for x in ['1-sigma', '1 sigma', '1시그마', '범위', 'range']) and '2' not in c.lower()), None)
        if not r1_col and len(cols) > 4:
            r1_col = cols[4]
            
        # 2시그마 범위 컬럼 매칭
        r2_col = next((c for c in filtered_df.columns if any(x in c.lower() for x in ['2-sigma', '2 sigma', '2시그마'])), None)
        
        if price_col and r1_col and r2_col:
            # 스마트폰 화면 가로폭에 맞게 줄임
            table_lines = [f"{'Ticker':<7} {'Price':<8} {'1-Sigma':<16} {'2-Sigma':<16}"]
            table_lines.append("-" * 50)
            for _, row in filtered_df.iterrows():
                ticker = str(row.get(ticker_col, ''))[:6]
                price = str(row.get(price_col, ''))[:7]
                # 공백과 달러 기호 제거로 가독성 확보
                r1 = str(row.get(r1_col, 'N/A')).replace('$', '').replace(' ', '')
                r2 = str(row.get(r2_col, 'N/A')).replace('$', '').replace(' ', '')
                table_lines.append(f"{ticker:<7} {price:<8} {r1:<16} {r2:<16}")
            
            formatted_table = "\n".join(table_lines)
        else:
            # 예외 상황 시 원본 테이블 전송
            formatted_table = filtered_df.to_string(index=False)

        # 백틱(```)으로 감싸서 고정폭 폰트 적용
        msg = f"📊 *{datetime.now().strftime('%Y-%m-%d')} 주식 예상 변동폭 (1 & 2시그마)*\n\n" + "```\n" + formatted_table + "\n```"
        
        # 3. 텔레그램 전송
        api_domain = "api.telegram.org"
        telegram_url = "https://" + api_domain + "/bot" + str(TOKEN) + "/sendMessage"
        requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_job()
