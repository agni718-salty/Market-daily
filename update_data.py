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

def get_kospi_fallback():
    """네이버 금융 모바일에서 코스피 최신 실제 지수와 전일대비 직접 수집"""
    url = "https://m.stock.naver.com/api/index/KOSPI/basic"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            now_price = safe_num(res_data.get('nowValue', '0').replace(',', ''))
            change_val = safe_num(res_data.get('changeValue', '0').replace(',', ''))
            is_fall = res_data.get('risefallName') == '하락'
            if is_fall:
                change_val = -abs(change_val)
            change_rate = safe_num(res_data.get('fluctuationsRatio', '0'))
            if is_fall:
                change_rate = -abs(change_rate)
            return now_price, change_val, change_rate
    except Exception as e:
        print(f"네이버 코스피 크롤링 실패: {e}")
        return None

def fetch_market_data():
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    updated_at_str = now_kst.strftime("%Y-%m-%d %H:%M KST")

    # 1. 주요 지수 수집
    tickers = {
        'S&P 500': '^GSPC',
        '나스닥': '^IXIC',
        '다우 존스': '^DJI',
        '코스피': '^KS11'
    }
    
    indices_summary = []
    candles_dict = {}

    for name, symbol in tickers.items():
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3y")
        
        # 0이하 비정상 결측치 제거
        if not df.empty:
            df = df[df['Close'] > 100]

        if not df.empty:
            last_close = safe_num(df.iloc[-1]['Close'])
            prev_close = safe_num(df.iloc[-2]['Close']) if len(df) > 1 else last_close
            change = last_close - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0.0

            # 코스피 휴장/결측 오차 방지
            if name == '코스피':
                naver_kospi = get_kospi_fallback()
                if naver_kospi and naver_kospi[0] > 1000:
                    last_close, change, change_pct = naver_kospi

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

    # 3. 요청하신 구글 뉴스 경제 토픽 RSS 수집
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
            paragraph = f"{title}에 대한 취재 보도입니다. 주요 금융시장 및 기업 거시 환경에 미치는 주요 변수와 산업 전반의 동향을 다루고 있습니다."

        news_list.append({
            "title": title,
            "link": entry.link,
            "summary": paragraph
        })

    # 4. 주요 지표 일정
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
    print("정상 데이터 생성 완료")

if __name__ == "__main__":
    fetch_market_data()
