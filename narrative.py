"""Narrative Hub — 뉴스 버즈·헤드라인 톤·애널리스트 모멘텀 등 '시장 내러티브' 프록시.

내러티브 경제학(Shiller): 스토리의 확산이 가격을 움직인다는 관점에서, 무료로 측정
가능한 신호만 골라 근사한다. Streamlit·yfinance에 의존하지 않는 순수 함수 모음.

⚠️ 정직한 한계: 무료 뉴스 API(yfinance)는 과거 임의 시점의 방대한 기사 아카이브를
제공하지 않고, 현재 시점 기준 최근 소수 기사만 준다. 그래서 "과거 평균 대비 뉴스량
z-score" 같은 정교한 시계열 지표는 만들 수 없다 — 대신 ①수집 한도 대비 현재 노출량(버즈),
②헤드라인 평균 감성(톤), ③애널리스트 컨센서스의 최근 수개월 변화(모멘텀)로 근사한다.
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError:  # 미설치 환경에선 감성분석 없이 중립(0.0)으로 폴백
    SentimentIntensityAnalyzer = None

# VADER는 일반/소셜미디어 어휘 기준이라 금융 헤드라인엔 둔감함(예: "beats", "plunge"를
# 못 알아들음) — 자주 나오는 금융 용어를 소폭 보강한다. 완벽한 금융 감성분석기는 아니다.
_FINANCE_LEXICON = {
    "beats": 2.0, "beat": 2.0, "surges": 2.5, "surge": 2.5, "soars": 2.8, "soar": 2.8,
    "rally": 2.0, "rallies": 2.0, "upgrade": 2.2, "upgraded": 2.2, "outperform": 2.0,
    "bullish": 2.0, "raises": 1.5, "raised": 1.5, "expands": 1.2, "record high": 2.5,
    "plunge": -2.8, "plunges": -2.8, "plunged": -2.8, "tumbles": -2.5, "tumble": -2.5,
    "slump": -2.2, "downgrade": -2.2, "downgraded": -2.2, "miss": -1.8, "misses": -1.8,
    "missed": -1.8, "lawsuit": -1.5, "bankruptcy": -3.0, "layoffs": -2.0, "recall": -1.8,
    "bearish": -2.0, "cuts": -1.2, "slashed": -2.0, "warns": -1.5, "warning": -1.5,
    "probe": -1.8, "investigation": -1.8, "selloff": -2.2, "sell-off": -2.2,
}

_analyzer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None and SentimentIntensityAnalyzer is not None:
        _analyzer = SentimentIntensityAnalyzer()
        _analyzer.lexicon.update(_FINANCE_LEXICON)
    return _analyzer


def score_headline(title: str) -> float:
    """헤드라인 감성 점수 -1(매우 부정)~+1(매우 긍정). 분석기 불가 시 0.0(중립)."""
    an = _get_analyzer()
    if an is None or not title:
        return 0.0
    return an.polarity_scores(title)["compound"]


def _parse_time(pub) -> datetime | None:
    if pub is None:
        return None
    if isinstance(pub, (int, float)):
        try:
            return datetime.fromtimestamp(pub, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(pub, str):
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(pub, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def news_narrative(news: list[dict], limit_hint: int = 8) -> dict:
    """뉴스 리스트로부터 버즈(노출량)·톤(헤드라인 평균 감성)을 산출.
    buzz: 0~100 (수집 한도 대비 현재 노출량 — '얼마나 화제인가'의 근사치).
    sentiment: -100~100 (헤드라인 평균 톤)."""
    if not news:
        return {"available": False, "buzz": 0, "sentiment": 0, "label": "데이터 없음",
                "recent_within_3d": 0, "articles": []}
    now = datetime.now(timezone.utc)
    scored = []
    recent_3d = 0
    for n in news:
        t = _parse_time(n.get("time"))
        s = score_headline(n.get("title", ""))
        if t and (now - t).days <= 3:
            recent_3d += 1
        scored.append({**n, "sentiment": s, "parsed_time": t})
    buzz = round(min(len(news) / max(limit_hint, 1), 1.0) * 100)
    sentiment_avg = sum(a["sentiment"] for a in scored) / len(scored)
    sentiment_100 = round(sentiment_avg * 100)
    if sentiment_100 >= 30:
        label = "긍정적"
    elif sentiment_100 <= -30:
        label = "부정적"
    else:
        label = "중립"
    return {"available": True, "buzz": buzz, "sentiment": sentiment_100, "label": label,
            "recent_within_3d": recent_3d, "articles": scored}


_PERIOD_ORDER = {"0m": 0, "-1m": 1, "-2m": 2, "-3m": 3}


def analyst_momentum(rec_rows: list[dict]) -> dict:
    """yfinance Ticker.recommendations를 records(list[dict])로 받아, 최근 수개월 애널리스트
    컨센서스가 강세/약세로 움직이는지 진단. (period: '0m'=이번달 ~ '-3m'=3개월전)"""
    def _bull_score(row):
        sb, b, h, s, ss = (row.get(k, 0) or 0 for k in
                           ("strongBuy", "buy", "hold", "sell", "strongSell"))
        total = sb + b + h + s + ss
        if not total:
            return None
        return (sb * 2 + b - s - ss * 2) / total

    if not rec_rows:
        return {"available": False}
    scored = [(r.get("period"), _bull_score(r)) for r in rec_rows]
    scored = [x for x in scored if x[1] is not None and x[0] in _PERIOD_ORDER]
    if len(scored) < 2:
        return {"available": False}
    scored.sort(key=lambda x: _PERIOD_ORDER[x[0]])
    latest = scored[0][1]
    oldest = scored[-1][1]
    delta = latest - oldest
    if delta > 0.1:
        trend = "개선(더 강세)"
    elif delta < -0.1:
        trend = "악화(더 약세)"
    else:
        trend = "횡보"
    return {"available": True, "latest_score": round(latest, 2), "trend": trend,
            "delta": round(delta, 2), "history": scored}


def search_interest(keyword: str):
    """Google Trends 검색 관심도(12개월, pandas.Series). 실패 시 조용히 None 반환
    (비공식 API라 요청 제한·구조변경에 취약 — 실패해도 화면에서 자연스럽게 숨겨짐)."""
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload([keyword], timeframe="today 12-m")
        df = pytrends.interest_over_time()
        if df is None or df.empty or keyword not in df.columns:
            return None
        return df[keyword]
    except Exception:
        return None
