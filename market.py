"""yfinance 기반 시장 데이터 조회.

Streamlit에 의존하지 않는 순수 함수. 캐싱은 호출자(app.py)가 st.cache_data로 감싼다.
무료 Yahoo 데이터는 일반장 시세 기준 실시간~15분 지연(거래소별 상이).
"""
from __future__ import annotations

import yfinance as yf


def _num(x):
    try:
        if x is None:
            return None
        f = float(x)
        return f if f == f else None  # NaN 제거
    except (TypeError, ValueError):
        return None


def get_quote(symbol: str) -> dict:
    """현재가/변동률 등 빠른 시세. fast_info 우선, 실패 시 info 폴백."""
    t = yf.Ticker(symbol)
    out = {"symbol": symbol.upper(), "price": None, "prev_close": None,
           "change_pct": None, "currency": None}
    try:
        fi = t.fast_info
        out["price"] = _num(fi.get("lastPrice"))
        out["prev_close"] = _num(fi.get("previousClose"))
        out["currency"] = fi.get("currency")
    except Exception:
        pass
    if out["price"] is not None and out["prev_close"]:
        out["change_pct"] = (out["price"] - out["prev_close"]) / out["prev_close"] * 100.0
    return out


def get_fundamentals(symbol: str) -> dict:
    """밸류에이션/펀더멘털 지표 묶음."""
    t = yf.Ticker(symbol)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    if price is None:
        try:
            price = _num(t.fast_info.get("lastPrice"))
        except Exception:
            price = None

    ebitda = _num(info.get("ebitda"))
    ev = _num(info.get("enterpriseValue"))
    return {
        "symbol": symbol.upper(),
        "name": info.get("shortName") or info.get("longName") or symbol.upper(),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": price,
        "market_cap": _num(info.get("marketCap")),
        "enterprise_value": ev,
        "trailing_pe": _num(info.get("trailingPE")),
        "forward_pe": _num(info.get("forwardPE")),
        "peg": _num(info.get("pegRatio")),
        "price_to_book": _num(info.get("priceToBook")),
        "price_to_sales": _num(info.get("priceToSalesTrailing12Months")),
        "ev_ebitda": (ev / ebitda if ev and ebitda else None),
        "ebitda": ebitda,
        "profit_margin": _num(info.get("profitMargins")),
        "revenue_growth": _num(info.get("revenueGrowth")),
        "earnings_growth": _num(info.get("earningsGrowth")),
        "eps_trailing": _num(info.get("trailingEps")),
        "eps_forward": _num(info.get("forwardEps")),
        "total_debt": _num(info.get("totalDebt")),
        "total_cash": _num(info.get("totalCash")),
        "free_cashflow": _num(info.get("freeCashflow")),
        "operating_cashflow": _num(info.get("operatingCashflow")),
        "debt_to_equity": _num(info.get("debtToEquity")),
        "shares_out": _num(info.get("sharesOutstanding")),
        "short_pct_float": _num(info.get("shortPercentOfFloat")),
        "beta": _num(info.get("beta")),
        "target_mean": _num(info.get("targetMeanPrice")),
        "recommendation": info.get("recommendationKey"),
        "fifty_two_high": _num(info.get("fiftyTwoWeekHigh")),
        "fifty_two_low": _num(info.get("fiftyTwoWeekLow")),
    }


def get_history(symbol: str, period: str = "1y", interval: str = "1d"):
    """가격 히스토리(차트용) DataFrame."""
    t = yf.Ticker(symbol)
    try:
        return t.history(period=period, interval=interval)
    except Exception:
        import pandas as pd
        return pd.DataFrame()


MARKET_INDICES = [("NASDAQ", "^IXIC"), ("S&P 500", "^GSPC")]


def get_market_indices() -> list[dict]:
    """주요 지수(나스닥/S&P500) 시세 — 사이드바 상시 표시용."""
    out = []
    for name, sym in MARKET_INDICES:
        q = get_quote(sym)
        out.append({"name": name, "price": q.get("price"),
                    "change_pct": q.get("change_pct")})
    return out


def get_analyst_recommendations(symbol: str) -> list[dict]:
    """최근 수개월 애널리스트 추천 분포(월별 strongBuy/buy/hold/sell/strongSell 카운트).
    narrative.analyst_momentum()의 입력으로 쓰인다."""
    t = yf.Ticker(symbol)
    try:
        df = t.recommendations
        return df.to_dict("records") if df is not None and not df.empty else []
    except Exception:
        return []


def get_recent_news(symbol: str, limit: int = 8) -> list[dict]:
    """최근 뉴스 헤드라인(촉매 기록 참고용)."""
    t = yf.Ticker(symbol)
    items = []
    try:
        raw = t.news or []
    except Exception:
        raw = []
    for n in raw[:limit]:
        content = n.get("content", n)  # 신규 yfinance 스키마 대응
        title = content.get("title") or n.get("title")
        pub = content.get("pubDate") or n.get("providerPublishTime")
        publisher = (content.get("provider", {}) or {}).get("displayName") \
            or n.get("publisher")
        link = ""
        if isinstance(content.get("clickThroughUrl"), dict):
            link = content["clickThroughUrl"].get("url", "")
        link = link or n.get("link", "")
        if title:
            items.append({"title": title, "publisher": publisher,
                          "time": pub, "link": link})
    return items
