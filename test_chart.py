"""chart.py 로직 테스트 — 합성 데이터로 추세탐지/구간/촉매매칭/Figure 생성 검증."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd
import chart as CH


def _synthetic():
    """상승→하락→상승(N자) — 데드크로스 1개 + 골든크로스 1개가 나와야."""
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="America/New_York")
    a, b = n // 3, 2 * n // 3
    up1 = np.linspace(80, 125, a)
    down = np.linspace(125, 70, b - a)
    up2 = np.linspace(70, 145, n - b)
    close = np.concatenate([up1, down, up2]) + np.random.RandomState(0).normal(0, 0.3, n)
    df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                       "Close": close}, index=idx)
    return df


def test_detect_trend_changes():
    df = _synthetic()
    changes = CH.detect_trend_changes(df, 20, 50)
    assert changes, "전환점이 하나도 안 나옴"
    types = [c["type"] for c in changes]
    assert "down" in types and "up" in types, types
    # V자이므로 down 이 up 보다 먼저
    first_down = next(i for i, c in enumerate(changes) if c["type"] == "down")
    first_up = next(i for i, c in enumerate(changes) if c["type"] == "up")
    assert first_down < first_up, "하락전환이 상승전환보다 먼저여야 함"
    print(f"  [ok] 전환점 {len(changes)}개 탐지: {types}")


def test_segments_cover_range():
    df = _synthetic()
    changes = CH.detect_trend_changes(df, 20, 50)
    segs = CH._segments(df, changes)
    assert segs[0]["x0"] == df.index[0]
    assert segs[-1]["x1"] == df.index[-1]
    print(f"  [ok] 추세 구간 {len(segs)}개, 전체 범위 커버")


def test_match_catalysts():
    df = _synthetic()
    cats = [
        {"date": "2024-03-15", "kind": "악재", "headline": "가이던스 하향", "note": "수요둔화",
         "reflected_pct": 40},
        {"date": "2099-01-01", "kind": "호재", "headline": "범위밖", "note": ""},  # 제외돼야
    ]
    m = CH._match_catalysts(df, cats)
    assert len(m) == 1, f"범위 밖 촉매가 걸러지지 않음: {m}"
    assert m[0]["kind"] == "악재"
    assert df.index[0] <= pd.Timestamp(m[0]["x"]).tz_convert(df.index.tz) <= df.index[-1]
    print(f"  [ok] 촉매 매칭: 범위내 1건, 범위밖 제외")


def test_build_figure_line_and_candle():
    df = _synthetic()
    cats = [{"date": "2024-04-01", "kind": "호재", "headline": "신제품", "note": "",
             "reflected_pct": 30}]
    f1 = CH.build_figure(df, "line", interval="1d", catalysts=cats)
    f2 = CH.build_figure(df, "candle", interval="1d", catalysts=cats)
    assert len(f1.data) >= 1 and len(f2.data) >= 1
    # candle 모드엔 SMA 2개 + 캔들 = 3 트레이스 이상
    assert any(t.type == "candlestick" for t in f2.data)
    print(f"  [ok] Figure 생성: line {len(f1.data)} traces, candle {len(f2.data)} traces")


def test_build_figure_volume_panel():
    df = _synthetic()
    df["Volume"] = np.random.RandomState(1).randint(1e6, 5e6, len(df))
    f = CH.build_figure(df, "candle", interval="1d", show_volume=True)
    assert any(t.type == "bar" and t.name == "Volume" for t in f.data), "거래량 막대 없음"
    # 가격/거래량 패널로 y축 분할되었는지
    assert f.layout.yaxis.domain[0] > 0.2, "가격 패널 domain 미조정"
    assert f.layout.yaxis2.domain[1] <= 0.2, "거래량 패널 domain 미조정"
    # show_volume=False 이면 거래량 트레이스 없음
    f0 = CH.build_figure(df, "candle", interval="1d", show_volume=False)
    assert not any(t.type == "bar" for t in f0.data)
    print("  [ok] 거래량 패널: 막대 트레이스 + y축 분할, 토글 OFF 시 미표시")


def test_build_figure_empty():
    f = CH.build_figure(pd.DataFrame(), "line", interval="1d")
    assert f is not None  # 빈 데이터에도 크래시 없음
    print("  [ok] 빈 데이터 → 크래시 없음")


def test_ma_analysis():
    # 단조 상승 → 정배열/강한 상승추세, 가격이 모든 MA 위
    idx = pd.date_range("2023-01-01", periods=200, freq="D")
    up = pd.DataFrame({"Close": np.linspace(50, 150, 200)}, index=idx)
    a = CH.ma_analysis(up)
    assert a["available"]
    assert set(a["mas"]) == {5, 20, 60, 120}, a["mas"].keys()
    assert a["alignment"] == "정배열", a["alignment"]
    assert a["verdict"].startswith("강한 상승"), a["verdict"]
    assert all(a["above"].values()), "상승장인데 가격이 MA 아래"
    # 단조 하락 → 역배열/강한 하락추세
    down = pd.DataFrame({"Close": np.linspace(150, 50, 200)}, index=idx)
    b = CH.ma_analysis(down)
    assert b["alignment"] == "역배열" and b["verdict"].startswith("강한 하락"), b["verdict"]
    # 데이터 부족 방어
    short = pd.DataFrame({"Close": [1, 2, 3]})
    assert CH.ma_analysis(short)["available"] is False
    print(f"  [ok] ma_analysis: 상승={a['verdict']}, 하락={b['verdict']}")


def test_latest_signal():
    df = _synthetic()  # 마지막 구간이 상승(up2) → 최근 추세 up 기대
    sig = CH.latest_signal(df, "1d", recent_bars=5)
    assert sig["trend"] in ("up", "down"), sig
    assert sig["trend"] == "up", f"마지막 상승 구간인데 {sig['trend']}"
    # 빈 데이터 방어
    empty = CH.latest_signal(pd.DataFrame(), "1d")
    assert empty["trend"] is None and empty["recent"] is None
    # recent 구조 검증(전환이 최근이면 dict, 아니면 None)
    if sig["recent"] is not None:
        assert set(sig["recent"]) == {"type", "date", "bars_ago"}
    print(f"  [ok] latest_signal: trend={sig['trend']}, recent={sig['recent'] is not None}")


def test_build_tv_panes_line_and_candle():
    df = _synthetic()
    cats = [{"date": "2024-04-01", "kind": "호재", "headline": "신제품", "note": "",
             "reflected_pct": 30}]
    line_panes = CH.build_tv_panes(df, "line", interval="1d", catalysts=cats)
    candle_panes = CH.build_tv_panes(df, "candle", interval="1d", catalysts=cats)
    assert len(line_panes) == 1, "거래량 미지정 시 가격 pane 1개여야 함"
    assert line_panes[0]["series"][0]["type"] == "Area"
    assert len(candle_panes[0]["series"]) == 3, "캔들모드는 가격+SMA2개 = 3 series"
    assert candle_panes[0]["series"][0]["type"] == "Candlestick"
    # 촉매 마커가 첫 series에 붙었는지
    assert "markers" in line_panes[0]["series"][0]
    assert any(m["text"].startswith("★") for m in line_panes[0]["series"][0]["markers"])
    print(f"  [ok] TV panes: line 1개 series타입=Area, candle 3 series(가격+SMA2), 마커 포함")


def test_build_tv_panes_volume_and_empty():
    df = _synthetic()
    df["Volume"] = np.random.RandomState(2).randint(1e6, 5e6, len(df))
    panes = CH.build_tv_panes(df, "candle", interval="1d", show_volume=True)
    assert len(panes) == 2, "거래량 ON이면 pane 2개(가격+거래량)"
    assert panes[1]["series"][0]["type"] == "Histogram"
    assert panes[1]["series"][0]["data"][0]["color"] in (CH.GREEN, CH.RED)
    panes_off = CH.build_tv_panes(df, "candle", interval="1d", show_volume=False)
    assert len(panes_off) == 1
    assert CH.build_tv_panes(pd.DataFrame(), "line") == []
    print("  [ok] TV panes: 거래량 ON→2pane/OFF→1pane, 빈데이터→[]")


def test_trend_summary():
    df = _synthetic()
    cats = [{"date": "2024-03-20", "kind": "악재", "headline": "하향", "note": "",
             "reflected_pct": 50}]
    rows = CH.trend_summary(df, "1d", cats)
    assert rows, "요약이 비어있음"
    assert rows[0]["date"] >= rows[-1]["date"]  # 최신순
    assert all("catalysts" in r for r in rows)
    print(f"  [ok] trend_summary {len(rows)}개 (최신순), 촉매 연결 OK")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    print(f"Running {len(tests)} chart tests...\n")
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
