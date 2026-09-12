import json
import datetime
import yfinance as yf
import feedparser
import re
import math

def clean_html(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def safe_num(val, default=0.0):
    if val is None or math.isnan(val):
        return default
    return float(val)

def fetch_market_data():
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    updated_at_str = now_kst.strftime("%Y-%m-%d %H:%M KST")

    # 1. 지수 데이터 수집 (최대 3년치)
    tickers = {
        'S&P 500': '^GSPC',
        '나스닥': '^IXIC',
        '다우 존스': '^DJI',
        '코스피': '^KS11'
    }
    
    indices_summary = []
    sp500_candles = []

    for name, symbol in tickers.items():
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3y")
        if not df.empty:
            last_close = safe_num(df.iloc[-1]['Close'])
            prev_close = safe_num(df.iloc[-2]['Close']) if len(df) > 1 else last_close
            change = last_close - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0.0
            
            indices_summary.append({
                "name": name,
                "price": f"{last_close:,.2f}",
                "change": round(safe_num(change), 2),
                "change_pct": f"{safe_num(change_pct):+.2f}"
            })

            # S&P 500 인터랙티브 캔들 차트
            if symbol == '^GSPC':
                for idx, row in df.iterrows():
                    o = safe_num(row['Open'])
                    h = safe_num(row['High'])
                    l = safe_num(row['Low'])
                    c = safe_num(row['Close'])
                    if o and h and l and c:
                        sp500_candles.append({
                            "time": idx.strftime("%Y-%m-%d"),
                            "open": round(o, 2),
                            "high": round(h, 2),
                            "low": round(l, 2),
                            "close": round(c, 2)
                        })

    # 2. 환율 및 국채 금리 수집 (최근 3개월)
    macro_tickers = {
        '원/달러 환율': 'KRW=X',
        '미국채 10년물 금리': '^TNX',
        '미국채 30년물 금리': '^TYX'
    }
    macro_summary = []
    usdkrw_series = []

    for name, symbol in macro_tickers.items():
        t = yf.Ticker(symbol)
        df = t.history(period="3mo")
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

            if symbol == 'KRW=X':
                for idx, row in df.iterrows():
                    val = safe_num(row['Close'])
                    if val:
                        usdkrw_series.append({
                            "time": idx.strftime("%Y-%m-%d"),
                            "value": round(val, 2)
                        })

    # 3. 국내 10대 뉴스 수집
    feed_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(feed_url)
    
    news_list = []
    seen_titles = set()

    for entry in feed.entries:
        if len(news_list) >= 10:
            break
        raw_title = clean_html(entry.title)
        title = raw_title.split(' - ')[0] if ' - ' in raw_title else raw_title
        
        core_keyword = title[:15]
        if core_keyword in seen_titles:
            continue
        seen_titles.add(core_keyword)

        summary_text = clean_html(entry.get('summary', ''))
        if not summary_text or len(summary_text) < 30:
            summary_text = f"{title}에 대한 상세 취재 내용과 시장 파급 효과를 다룬 기사입니다. 거시 금융 환경 및 국내 산업 전반에 미칠 주요 변수를 포함하고 있습니다."

        sentences = [s.strip() for s in summary_text.replace('\n', ' ').split('. ') if s.strip()]
        if len(sentences) > 4:
            paragraph = '. '.join(sentences[:4]) + '.'
        elif len(sentences) >= 2:
            paragraph = '. '.join(sentences) + '.'
        else:
            paragraph = summary_text

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
            "sp500_candles": sp500_candles
        },
        "macro": {
            "summary": macro_summary,
            "usdkrw_series": usdkrw_series
        },
        "news": news_list,
        "schedules": schedules
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print("data.json 생성 완료")

if __name__ == "__main__":
    fetch_market_data()
