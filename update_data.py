import json
import datetime
import yfinance as yf
import feedparser
import re
import math
import urllib.request

def clean_html(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def safe_num(val, default=0.0):
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except:
        return default

def fetch_npay_market(target="KOSPI"):
    """
    네이버페이 증권 공식 모바일 API 호출
    차단 방지용 브라우저 헤더 및 Referer 탑재
    """
    url = f"https://m.stock.naver.com/api/index/{target}/basic"
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
        'Referer': 'https://m.stock.naver.com/',
        'Accept': 'application/json, text/plain, */*'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
            price = safe_num(data.get('nowValue', '0').replace(',', ''))
            change = safe_num(data.get('changeValue', '0').replace(',', ''))
            is_fall = data.get('risefallName') == '하락'
            if is_fall:
                change = -abs(change)
            change_pct = safe_num(data.get('fluctuationsRatio', '0'))
            if is_fall:
                change_pct = -abs(change_pct)
            return price, change, change_pct
    except Exception as e:
        print(f"네이버페이 증권 {target} 호출 실패: {e}")
        return None

def fetch_market_data():
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    updated_at_str = now_kst.strftime("%Y-%m-%d %H:%M KST")

    # 1. 주요 지수 수집 (미국 지수는 yfinance, 코스피는 네이버페이 증권 1순위)
    tickers = {
        'S&P 500': '^GSPC',
        '나스닥': '^IXIC',
        '다우 존스': '^DJI',
        '코스피': '^KS11'
    }
    
    indices_summary = []
    candles_dict = {}

    # 네이버페이 증권에서 실제 코스피 가져오기
    npay_kospi = fetch_npay_market("KOSPI")

    for name, symbol in tickers.items():
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3y")
        
        if not df.empty:
            df = df[df['Close'] > 0]

        if not df.empty:
            last_close = safe_num(df.iloc[-1]['Close'])
            prev_close = safe_num(df.iloc[-2]['Close']) if len(df) > 1 else last_close
            change = last_close - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0.0

            # 코스피는 네이버페이 증권의 실시간 종가 우선 적용
            if name == '코스피' and npay_kospi:
                last_close, change, change_pct = npay_kospi

            indices_summary.append({
                "name": name,
                "price": f"{last_close:,.2f}",
                "change": round(safe_num(change), 2),
                "change_pct": f"{safe_num(change_pct):+.2f}"
            })

            # 지수별 캔들 데이터 생성
            c_list = []
            for idx, row in df.iterrows():
                o = safe_num(row['Open'])
                h = safe_num(row['High'])
                l = safe_num(row['Low'])
                c = safe_num(row['Close'])
                
                # 야후 파이낸스의 코스피 7,000대 오류치 완벽 차단 (정상 범위만 수집)
                if name == '코스피' and (c > 4500 or c < 1000):
                    continue

                if o > 0 and h > 0 and l > 0 and c > 0:
                    c_list.append({
                        "time": idx.strftime("%Y-%m-%d"),
                        "open": round(o, 2),
                        "high": round(h, 2),
                        "low": round(l, 2),
                        "close": round(c, 2)
                    })
            candles_dict[name] = c_list

    # 2. 통화 & 거시 금리 수집
    macro_tickers = {
        '원/달러 환율': 'KRW=X',
        '미국채 10년물 금리': '^TNX',
        '미국채 30년물 금리': '^TYX'
    }
    macro_summary = []
    macro_series_dict = {}

    for name, symbol in macro_tickers.items():
        t = yf.Ticker(symbol)
        df = t.history(period="3mo")
        df = df[df['Close'] > 0]
        
        if not df.empty:
            last_val = safe_num(df.iloc[-1]['Close'])
            prev_val = safe_num(df.iloc[-2]['Close']) if len(df) > 1 else last_val
            diff = last_val - prev_val
            
            unit = "원" if "환율" in name else "%"
            macro_summary.append({
                "name": name,
                "value": f"{last_val:,.2f} {unit}",
                "change": round(safe_num(diff), 2),
                "change_str": f"{safe_num(diff):+.2f}{unit}"
            })

            s_list = []
            for idx, row in df.iterrows():
                val = safe_num(row['Close'])
                if val > 0:
                    s_list.append({
                        "time": idx.strftime("%Y-%m-%d"),
                        "value": round(val, 2)
                    })
            macro_series_dict[name] = s_list

    # 3. 구글 뉴스 경제 토픽 RSS 수집
    feed_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtdHZHZ0pMVWlnQVAB?hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(feed_url)
    
    news_list = []
    seen_titles = set()

    for entry in feed.entries:
        if len(news_list) >= 10:
            break
        raw_title = clean_html(entry.title)
        title = raw_title.split(' - ')[0] if ' - ' in raw_title else raw_title
        
        core_keyword = title[:12]
        if core_keyword in seen_titles:
            continue
        seen_titles.add(core_keyword)

        summary_raw = clean_html(entry.get('summary', ''))
        clean_text = re.sub(r'https?://\S+|v\.daum\.net\S*', '', summary_raw)
        
        sentences = [s.strip() for s in re.split(r'[\.\?!]\s+', clean_text) if len(s.strip()) > 15]
        if len(sentences) >= 3:
            paragraph = '. '.join(sentences[:4]) + '.'
        else:
            paragraph = f"{title}에 대한 상세 취재 보도입니다. 금융시장 및 국내외 거시 경제 환경에 미칠 주요 변수와 산업 전반의 동향을 다루고 있습니다."

        news_list.append({
            "title": title,
            "link": entry.link,
            "summary": paragraph
        })

    # 4. 주요 일정
    schedules = [
        {"title": "미국 8월 생산자물가지수 (PPI)", "desc": "발표 완료 (원자재·에너지 반등으로 도매물가 상승 흐름 확인)"},
        {"title": "미국 8월 소비자물가지수 (CPI / Core CPI)", "desc": "헤드라인 3.4%(예상 부합), 근원 물가 2.4% 수준 유지"},
        {"title": "차주 핵심 일정", "desc": "미 연준(Fed) 9월 FOMC 기준금리 결정 및 분기 점도표 공개"}
    ]

    output_data = {
        "updated_at": updated_at_str,
        "indices": {
            "summary": indices_summary,
            "candles_dict": candles_dict
        },
        "macro": {
            "summary": macro_summary,
            "series_dict": macro_series_dict
        },
        "news": news_list,
        "schedules": schedules
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print("Npay 증권 연동 및 정상 데이터 생성 완료")

if __name__ == "__main__":
    fetch_market_data()
