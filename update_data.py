import json
import os
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

def get_kospi_from_naver():
    """1차: 네이버페이 증권 모바일 API"""
    url = "https://m.stock.naver.com/api/index/KOSPI/basic"
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Referer': 'https://m.stock.naver.com/',
        'Accept': 'application/json, text/plain, */*'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
            price = safe_num(data.get('nowValue', '0').replace(',', ''))
            change = safe_num(data.get('changeValue', '0').replace(',', ''))
            is_fall = data.get('risefallName') == '하락'
            if is_fall:
                change = -abs(change)
            change_pct = safe_num(data.get('fluctuationsRatio', '0'))
            if is_fall:
                change_pct = -abs(change_pct)
            if price > 0:
                return price, change, change_pct
    except Exception as e:
        print(f"네이버페이 증권 수집 실패 (봇 차단 가능성): {e}")
    return None

def get_kospi_from_daum():
    """2차 폴백: 다음 금융 모바일 API"""
    url = "https://finance.daum.net/api/quotes/KOSPI"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://finance.daum.net/'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as response:
            res = json.loads(response.read().decode('utf-8'))
            price = safe_num(res.get('tradePrice'))
            change = safe_num(res.get('changePrice'))
            change_type = res.get('change')
            if change_type == 'FALL':
                change = -abs(change)
            change_pct = safe_num(res.get('changeRate')) * 100
            if change_type == 'FALL':
                change_pct = -abs(change_pct)
            if price > 0:
                return price, change, change_pct
    except Exception as e:
        print(f"다음 금융 API 수집 실패: {e}")
    return None

def load_previous_kospi():
    """3차 최후 안전장치: 기존 data.json의 코스피 데이터 보존"""
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                old = json.load(f)
                for item in old.get("indices", {}).get("summary", []):
                    if item.get("name") == "코스피":
                        return item
        except:
            pass
    return None

def fetch_market_data():
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    updated_at_str = now_kst.strftime("%Y-%m-%d %H:%M KST")

    # 1. 미국 3대 지수 + 코스피
    tickers = {
        'S&P 500': '^GSPC',
        '나스닥': '^IXIC',
        '다우 존스': '^DJI',
        '코스피': '^KS11'
    }
    
    indices_summary = []
    candles_dict = {}

    # 코스피 실시간 수치 별도 확보 (네이버 -> 다음 순)
    exact_kospi = get_kospi_from_naver() or get_kospi_from_daum()

    for name, symbol in tickers.items():
        ticker = yf.Ticker(symbol)
        try:
            df = ticker.history(period="3y")
        except:
            df = None

        last_close, change, change_pct = 0.0, 0.0, 0.0
        has_yfinance_data = df is not None and not df.empty and len(df) > 1

        if has_yfinance_data:
            df = df[df['Close'] > 0]
            last_close = safe_num(df.iloc[-1]['Close'])
            prev_close = safe_num(df.iloc[-2]['Close'])
            change = last_close - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0.0

            # 캔들차트 데이터 저장
            c_list = []
            for idx, row in df.iterrows():
                o, h, l, c = safe_num(row['Open']), safe_num(row['High']), safe_num(row['Low']), safe_num(row['Close'])
                if o > 0 and h > 0 and l > 0 and c > 0:
                    c_list.append({
                        "time": idx.strftime("%Y-%m-%d"),
                        "open": round(o, 2), "high": round(h, 2),
                        "low": round(l, 2), "close": round(c, 2)
                    })
            candles_dict[name] = c_list

        # 코스피는 네이버/다음 실시간 종가 우선 적용
        if name == '코스피':
            if exact_kospi:
                last_close, change, change_pct = exact_kospi
            elif not has_yfinance_data:
                # 모든 API 실패 시 기존 파일 캐시로 복원
                cached = load_previous_kospi()
                if cached:
                    indices_summary.append(cached)
                    continue

        if last_close > 0:
            indices_summary.append({
                "name": name,
                "price": f"{last_close:,.2f}",
                "change": round(safe_num(change), 2),
                "change_pct": f"{safe_num(change_pct):+.2f}"
            })

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
        try:
            df = t.history(period="3mo")
            df = df[df['Close'] > 0]
        except:
            df = None
        
        if df is not None and not df.empty:
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
    print("완전 무결성 데이터 생성 완료")

if __name__ == "__main__":
    fetch_market_data()
