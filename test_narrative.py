"""narrative.py 로직 테스트 — 버즈/감성/애널리스트 모멘텀/검색관심도 안전성 검증."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import narrative as NA


def test_score_headline_finance_lexicon():
    """일반 VADER가 놓치는 금융 어휘(beats/plunge 등)를 보강 사전으로 잡아내는지."""
    pos = NA.score_headline("Apple beats earnings expectations, stock surges")
    neg = NA.score_headline("Company faces lawsuit, shares plunge after warning")
    neutral = NA.score_headline("")
    assert pos > 0.3, f"긍정 헤드라인 점수가 낮음: {pos}"
    assert neg < -0.3, f"부정 헤드라인 점수가 낮음: {neg}"
    assert neutral == 0.0
    print(f"  [ok] 헤드라인 감성: 긍정={pos:.2f}, 부정={neg:.2f}, 빈문자열=0.0")


def test_news_narrative_buzz_and_sentiment():
    news = [
        {"title": "Company beats earnings, stock surges", "time": None},
        {"title": "Analysts upgrade stock after strong guidance", "time": None},
        {"title": "Neutral product announcement", "time": None},
        {"title": "Stock plunges on lawsuit news", "time": None},
    ]
    r = NA.news_narrative(news, limit_hint=8)
    assert r["available"] is True
    assert r["buzz"] == 50, f"버즈 계산 오류(4/8=50 기대): {r['buzz']}"
    assert "articles" in r and len(r["articles"]) == 4
    assert r["label"] in ("긍정적", "부정적", "중립")
    empty = NA.news_narrative([])
    assert empty["available"] is False and empty["buzz"] == 0
    print(f"  [ok] news_narrative: buzz={r['buzz']}, sentiment={r['sentiment']}, "
          f"label={r['label']}, 빈뉴스 방어 OK")


def test_news_narrative_recent_window():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    recent_ts = (now - timedelta(days=1)).timestamp()
    old_ts = (now - timedelta(days=30)).timestamp()
    news = [
        {"title": "Fresh news today", "time": recent_ts},
        {"title": "Old news a month ago", "time": old_ts},
    ]
    r = NA.news_narrative(news)
    assert r["recent_within_3d"] == 1, f"3일 이내 뉴스 카운트 오류: {r['recent_within_3d']}"
    print(f"  [ok] 최근 3일 이내 뉴스 카운트 정상: {r['recent_within_3d']}/2")


def test_analyst_momentum_trend():
    improving = [
        {"period": "0m", "strongBuy": 10, "buy": 10, "hold": 5, "sell": 0, "strongSell": 0},
        {"period": "-1m", "strongBuy": 5, "buy": 10, "hold": 8, "sell": 2, "strongSell": 0},
        {"period": "-2m", "strongBuy": 3, "buy": 8, "hold": 10, "sell": 4, "strongSell": 0},
    ]
    r = NA.analyst_momentum(improving)
    assert r["available"] is True
    assert r["trend"] == "개선(더 강세)", r
    assert r["delta"] > 0

    worsening = [
        {"period": "0m", "strongBuy": 1, "buy": 3, "hold": 10, "sell": 8, "strongSell": 3},
        {"period": "-1m", "strongBuy": 8, "buy": 15, "hold": 5, "sell": 1, "strongSell": 0},
    ]
    r2 = NA.analyst_momentum(worsening)
    assert r2["trend"] == "악화(더 약세)", r2

    assert NA.analyst_momentum([])["available"] is False
    assert NA.analyst_momentum([{"period": "0m", "strongBuy": 0, "buy": 0, "hold": 0,
                                 "sell": 0, "strongSell": 0}])["available"] is False
    print(f"  [ok] analyst_momentum: 개선/악화 추세 감지, 빈데이터/0표본 방어")


def test_search_interest_fails_safely():
    """pytrends가 예외를 던져도(비공식 API·요청제한 등) None으로 조용히 폴백해야 함."""
    import unittest.mock as mock
    with mock.patch("pytrends.request.TrendReq", side_effect=RuntimeError("blocked")):
        r = NA.search_interest("AAPL")
        assert r is None
    print("  [ok] Google Trends 실패 시 예외 없이 None 반환")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    print(f"Running {len(tests)} narrative tests...\n")
    failed = 0
    for t in tests:
        try:
            print(f"- {t.__name__}")
            t()
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {type(e).__name__}: {e}")
    print(f"\n{'='*50}\n{len(tests)-failed}/{len(tests)} passed"
          + ("" if not failed else f", {failed} FAILED"))
    raise SystemExit(1 if failed else 0)
