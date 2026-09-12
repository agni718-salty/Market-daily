import json
import datetime
import yfinance as yf
import feedparser
import re
import urllib.parse

def clean_html(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

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
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last
            change = last['Close'] - prev['Close']
            change_pct = (change / prev['Close']) * 100
            
            indices_summary.append({
                "name": name,
                "price": f"{last['Close']:,.2f}",
                "change": round(change, 2),
                "change_pct": f"{change_pct:+.2f}"
            })

            # S&P 500은 인터랙티브 캔들 차트 데이터로 가공
            if symbol == '^GSPC':
                for idx, row in df.iterrows():
                    sp500_candles.append({
                        "time": idx.strftime("%Y-%m-%d"),
                        "open": round(row['Open'], 2),
                        "high": round(row['High'], 2),
                        "low": round(row['Low'], 2),
                        "close": round(row['Close'], 2)
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
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last
            diff = last['Close'] - prev['Close']
            
            unit = "원" if "환율" in name else "%"
            macro_summary.append({
                "name": name,
                "value": f"{last['Close']:,.2f} {unit}",
                "change": round(diff, 2),
                "change_str": f"{diff:+.2f}{unit}"
            })

            if symbol == 'KRW=X':
                for idx, row in df.iterrows():
                    usdkrw_series.append({
                        "time": idx.strftime("%Y-%m-%d"),
                        "value": round(row['Close'], 2)
                    })

    # 3. 국내 10대 뉴스 수집 (네이버 뉴스 경제 메인 피드)
    feed_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(feed_url)
    
    news_list = []
    seen_titles = set()

    for entry in feed.entries:
        if len(news_list) >= 10:
            break
        raw_title = clean_html(entry.title)
        # 출처 분리
        title = raw_title.split(' - ')[0] if ' - ' in raw_title else raw_title
        
        # 중복 제목 필터링
        core_keyword = title[:15]
        if core_keyword in seen_titles:
            continue
        seen_titles.add(core_keyword)

        summary_text = clean_html(entry.get('summary', ''))
        if not summary_text or len(summary_text) < 30:
            summary_text = f"{title}에 대한 상세 취재 내용과 시장 파급 효과를 다룬 기사입니다. 거시 금융 환경 및 국내 산업 전반에 미칠 주요 변수를 포함하고 있습니다."

        # 기사 3~5줄 형태의 자연스러운 문장 단락 구성
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

    # 4. 주요 지표 일정
    schedules = [
        {"title": "미국 8월 생산자물가지수 (PPI)", "desc": "발표 완료 (원자재·유가 반등으로 전월비 반등 흐름 확인)"},
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
