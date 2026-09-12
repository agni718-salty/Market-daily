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
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except:
        return default

def fetch_market_data():
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    updated_at_str = now_kst.strftime("%Y-%m-%d %H:%M KST")

    # 1. 4대 주요 지수 (캔들 데이터 3년치 각각 수집)
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
        
        # 0값 제거 (거래 정지/휴장 결측치 보정)
        df = df[df['Close'] > 0]

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

            # 지수별 캔들 리스트 생성
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

    # 2. 거시 지표 3종 (3개월 시계열 각각 수집)
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

    # 3. 구글 뉴스 RSS 파싱 및 중복 언론사 찌꺼기 텍스트 정제
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

        # 요약문 정제 (기존 지저분한 RSS 링크/언론사 중복 텍스트 분리)
        summary_raw = clean_html(entry.get('summary', ''))
        # 반복 태그 및 url 잔여물 제거
        clean_text = re.sub(r'https?://\S+|v\.daum\.net\S*', '', summary_raw)
        
        sentences = [s.strip() for s in re.split(r'[\.\?!]\s+', clean_text) if len(s.strip()) > 15]
        if len(sentences) >= 3:
            paragraph = '. '.join(sentences[:4]) + '.'
        else:
            paragraph = f"{title}에 관한 상세 시장 분석 보도입니다. 해당 경제 이슈가 금융시장과 국내외 주요 산업 및 금리/환율 환경에 미칠 영향을 다루고 있습니다."

        news_list.append({
            "title": title,
            "link": entry.link,
            "summary": paragraph
        })

    # 4. 일정
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
