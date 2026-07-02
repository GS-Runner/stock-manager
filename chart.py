"""Robinhood 스타일 차트 + 추세 전환 탐지 + 촉매(내러티브) 오버레이.

- SMA 단/장기 크로스오버로 상승/하락 추세 시작 구간을 자동 탐지.
- 사용자가 기록한 촉매(호재/악재 + 메모)를 해당 날짜의 가격 위에 마커로 표시.
- plotly Figure를 반환하므로 Streamlit/네트워크에 비의존(테스트 용이).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

GREEN = "#00C805"   # Robinhood green
RED = "#FF5000"     # Robinhood red
DIM_GREEN = "rgba(0,200,5,0.10)"
DIM_RED = "rgba(255,80,0,0.10)"
GRID = "rgba(255,255,255,0.06)"


# 간격(interval)별 SMA 윈도우 기본값 (단기, 장기)
SMA_WINDOWS = {
    "intraday": (9, 21),
    "1d": (20, 50),
    "1wk": (10, 30),
    "1mo": (6, 12),
}


def sma_windows_for(interval: str) -> tuple[int, int]:
    if interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"):
        return SMA_WINDOWS["intraday"]
    return SMA_WINDOWS.get(interval, (20, 50))


def detect_trend_changes(df: pd.DataFrame, short: int, long: int) -> list[dict]:
    """단/장기 SMA 크로스오버 지점을 추세 전환점으로 반환.

    type='up'  : 골든크로스(단기>장기) → 상승 추세 시작
    type='down': 데드크로스(단기<장기) → 하락 추세 시작
    """
    if df is None or df.empty or len(df) < long + 1:
        return []
    close = df["Close"]
    s = close.rolling(short).mean()
    l = close.rolling(long).mean()
    diff = (s - l).dropna()
    if diff.empty:
        return []
    sign = np.sign(diff.values)
    changes: list[dict] = []
    prev = None
    for i, val in enumerate(sign):
        if val == 0:
            continue
        if prev is not None and val != prev:
            ts = diff.index[i]
            changes.append({
                "date": ts,
                "type": "up" if val > 0 else "down",
                "price": float(close.loc[ts]),
            })
        prev = val
    return changes


def _segments(df: pd.DataFrame, changes: list[dict]) -> list[dict]:
    """추세 전환점들로 [구간 시작, 끝, 방향] 리스트 생성(음영용)."""
    if not changes:
        return []
    segs = []
    start = df.index[0]
    # 첫 구간의 방향은 첫 전환의 반대
    cur_dir = "down" if changes[0]["type"] == "up" else "up"
    for ch in changes:
        segs.append({"x0": start, "x1": ch["date"], "dir": cur_dir})
        start = ch["date"]
        cur_dir = ch["type"]
    segs.append({"x0": start, "x1": df.index[-1], "dir": cur_dir})
    return segs


def _match_catalysts(df: pd.DataFrame, catalysts: list[dict]) -> list[dict]:
    """촉매 날짜를 차트 범위 내 가장 가까운 봉에 매칭."""
    if not catalysts or df is None or df.empty:
        return []
    idx = df.index
    idx_naive = idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx
    idx_vals = idx_naive.values.astype("datetime64[ns]")
    lo, hi = idx_naive[0], idx_naive[-1]
    out = []
    for c in catalysts:
        try:
            ts = pd.Timestamp(c["date"])
        except Exception:
            continue
        if ts < lo - pd.Timedelta(days=5) or ts > hi + pd.Timedelta(days=5):
            continue  # 차트 범위 밖
        pos = int(np.abs(idx_vals - np.datetime64(ts)).argmin())
        bar = idx[pos]
        out.append({
            "x": bar,
            "y": float(df["Close"].iloc[pos]),
            "kind": c.get("kind", "호재"),
            "headline": c.get("headline", ""),
            "note": c.get("note", ""),
            "reflected": c.get("reflected_pct"),
            "expected": c.get("expected_impact"),
        })
    return out


def _period_color(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return GREEN
    return GREEN if df["Close"].iloc[-1] >= df["Close"].iloc[0] else RED


def build_figure(df: pd.DataFrame, mode: str = "line", *,
                 interval: str = "1d", catalysts: list[dict] | None = None,
                 show_trend: bool = True, show_volume: bool = False,
                 title: str = "") -> go.Figure:
    """Robinhood 스타일 Figure 생성.

    mode: 'line'(영역 라인) | 'candle'(캔들 + SMA)
    show_volume=True 이면 하단에 거래량 막대 패널(별도 y축)을 추가한다.
    """
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(template="plotly_dark", height=420,
                          annotations=[dict(text="데이터 없음", showarrow=False)])
        return fig

    catalysts = catalysts or []
    short, long = sma_windows_for(interval)
    changes = detect_trend_changes(df, short, long) if show_trend else []

    # 추세 구간 음영
    if show_trend:
        for seg in _segments(df, changes):
            fig.add_vrect(x0=seg["x0"], x1=seg["x1"], line_width=0,
                          fillcolor=DIM_GREEN if seg["dir"] == "up" else DIM_RED,
                          layer="below")

    if mode == "candle":
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"],
            close=df["Close"], name="가격",
            increasing_line_color=GREEN, decreasing_line_color=RED,
            increasing_fillcolor=GREEN, decreasing_fillcolor=RED))
        # SMA 오버레이
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"].rolling(short).mean(),
                                 mode="lines", name=f"SMA{short}",
                                 line=dict(color="#7AA2FF", width=1)))
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"].rolling(long).mean(),
                                 mode="lines", name=f"SMA{long}",
                                 line=dict(color="#FFB020", width=1)))
    else:  # line / area (Robinhood)
        col = _period_color(df)
        fill_col = "rgba(0,200,5,0.08)" if col == GREEN else "rgba(255,80,0,0.08)"
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Close"], mode="lines", name="가격",
            line=dict(color=col, width=2), fill="tozeroy", fillcolor=fill_col,
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:.2f}<extra></extra>"))
        lo = float(df["Close"].min()) * 0.985
        hi = float(df["Close"].max()) * 1.015
        fig.update_yaxes(range=[lo, hi])

    # 추세 전환 마커 (▲상승 / ▼하락 시작)
    if show_trend and changes:
        up = [c for c in changes if c["type"] == "up"]
        dn = [c for c in changes if c["type"] == "down"]
        if up:
            fig.add_trace(go.Scatter(
                x=[c["date"] for c in up], y=[c["price"] for c in up],
                mode="markers", name="상승전환",
                marker=dict(symbol="triangle-up", size=12, color=GREEN,
                            line=dict(width=1, color="white")),
                hovertemplate="▲ 상승 추세 시작<br>%{x|%Y-%m-%d}<br>$%{y:.2f}<extra></extra>"))
        if dn:
            fig.add_trace(go.Scatter(
                x=[c["date"] for c in dn], y=[c["price"] for c in dn],
                mode="markers", name="하락전환",
                marker=dict(symbol="triangle-down", size=12, color=RED,
                            line=dict(width=1, color="white")),
                hovertemplate="▼ 하락 추세 시작<br>%{x|%Y-%m-%d}<br>$%{y:.2f}<extra></extra>"))

    # 촉매(내러티브) 마커
    matched = _match_catalysts(df, catalysts)
    for grp, color, sym in [("호재", GREEN, "star"), ("악재", RED, "star")]:
        pts = [m for m in matched if m["kind"] == grp]
        if not pts:
            continue
        texts = []
        for m in pts:
            r = f" · 반영 {m['reflected']:.0f}%" if m.get("reflected") is not None else ""
            note = f"<br>{m['note']}" if m.get("note") else ""
            texts.append(f"{'🟢' if grp=='호재' else '🔴'} {grp}: {m['headline']}{r}{note}")
        fig.add_trace(go.Scatter(
            x=[m["x"] for m in pts], y=[m["y"] for m in pts],
            mode="markers", name=grp,
            marker=dict(symbol=sym, size=14, color=color,
                        line=dict(width=1, color="white")),
            text=texts, hovertemplate="%{text}<br>%{x|%Y-%m-%d}<extra></extra>"))

    # 거래량 패널 (하단 별도 y축)
    vol_added = False
    if show_volume and "Volume" in df.columns and not df["Volume"].isna().all():
        if mode == "candle":
            bar_colors = [GREEN if c >= o else RED
                          for o, c in zip(df["Open"], df["Close"])]
        else:
            close = df["Close"]
            bar_colors = [GREEN] + [GREEN if close.iloc[i] >= close.iloc[i - 1]
                                    else RED for i in range(1, len(close))]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="거래량", yaxis="y2",
            marker_color=bar_colors, marker_line_width=0, opacity=0.5,
            hovertemplate="거래량 %{y:,.0f}<extra></extra>"))
        vol_added = True

    fig.update_layout(
        template="plotly_dark", height=540 if vol_added else 460, title=title,
        margin=dict(l=0, r=0, t=30 if title else 8, b=0),
        xaxis_rangeslider_visible=False, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                    bgcolor="rgba(0,0,0,0)"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    if vol_added:
        # 가격/거래량 패널로 세로 분할
        fig.update_layout(
            yaxis=dict(domain=[0.26, 1.0]),
            yaxis2=dict(domain=[0.0, 0.18], showgrid=False, zeroline=False,
                        title_text="거래량"),
        )
    return fig


def _recent_cross(close: pd.Series, sw: int, lw: int, recent: int = 7) -> dict | None:
    """단기SMA(sw) vs 장기SMA(lw)의 최근 골든/데드크로스. 없으면 None."""
    if close is None or len(close) < lw + 2:
        return None
    diff = (close.rolling(sw).mean() - close.rolling(lw).mean()).dropna()
    if len(diff) < 2:
        return None
    sign = np.sign(diff.values)
    for i in range(len(sign) - 1, 0, -1):
        if sign[i] != 0 and sign[i - 1] != 0 and sign[i] != sign[i - 1]:
            bars_ago = len(sign) - 1 - i
            if bars_ago <= recent:
                return {"type": "golden" if sign[i] > 0 else "dead",
                        "bars_ago": int(bars_ago)}
            return None
    return None


def ma_analysis(df: pd.DataFrame, windows: tuple = (5, 20, 60, 120)) -> dict:
    """이동평균선(기본 5·20·60·120일) 기준 현재 추세 분석.

    반환: available, price, mas{w:값}, gap{w:price대비%}, above{w:bool},
          alignment(정배열/역배열/혼조), verdict(요약), color, crosses{'5x20','20x60'}.
    """
    out: dict = {"available": False, "windows": windows}
    if df is None or df.empty or "Close" not in df.columns:
        return out
    close = df["Close"].dropna()
    if len(close) < min(windows) + 1:
        return out
    price = float(close.iloc[-1])
    mas = {w: float(close.rolling(w).mean().iloc[-1])
           for w in windows if len(close) >= w}
    if not mas:
        return out
    avail = [w for w in windows if w in mas]

    asc = all(mas[avail[i]] > mas[avail[i + 1]] for i in range(len(avail) - 1))
    desc = all(mas[avail[i]] < mas[avail[i + 1]] for i in range(len(avail) - 1))
    alignment = "정배열" if (asc and len(avail) >= 2) else \
                ("역배열" if (desc and len(avail) >= 2) else "혼조")

    above = {w: price >= mas[w] for w in avail}
    gap = {w: (price - mas[w]) / mas[w] * 100.0 for w in avail}
    n_above = sum(above.values())

    # 종합 판정
    if alignment == "정배열" and n_above == len(avail):
        verdict, color = "강한 상승추세 (정배열)", "green"
    elif alignment == "역배열" and n_above == 0:
        verdict, color = "강한 하락추세 (역배열)", "red"
    elif n_above >= max(1, len(avail) - 1):
        verdict, color = "상승 우위", "green"
    elif n_above <= min(1, len(avail) - 1):
        verdict, color = "하락 우위", "red"
    else:
        verdict, color = "혼조 / 방향 탐색", "orange"

    crosses = {}
    if 5 in mas and 20 in mas:
        crosses["5x20"] = _recent_cross(close, 5, 20)
    if 20 in mas and 60 in mas:
        crosses["20x60"] = _recent_cross(close, 20, 60)

    out.update({"available": True, "price": price, "mas": mas, "gap": gap,
                "above": above, "alignment": alignment, "verdict": verdict,
                "color": color, "crosses": crosses})
    return out


def latest_signal(df: pd.DataFrame, interval: str = "1d", recent_bars: int = 5) -> dict:
    """현재 추세 방향 + 최근 추세전환(스캐너/알림용).

    trend : 'up'/'down'/None (최근 봉의 단기SMA vs 장기SMA 부호)
    recent: 최근 recent_bars 이내 전환이 있으면 {type, date, bars_ago}, 없으면 None
    """
    out = {"trend": None, "recent": None}
    if df is None or df.empty:
        return out
    short, long = sma_windows_for(interval)
    close = df["Close"]
    diff = (close.rolling(short).mean() - close.rolling(long).mean()).dropna()
    if not diff.empty:
        v = float(diff.iloc[-1])
        out["trend"] = "up" if v > 0 else ("down" if v < 0 else None)
    changes = detect_trend_changes(df, short, long)
    if changes:
        last = changes[-1]
        try:
            pos = int(np.where(df.index == last["date"])[0][0])
            bars_ago = len(df) - 1 - pos
        except (IndexError, ValueError):
            bars_ago = None
        if bars_ago is not None and bars_ago <= recent_bars:
            out["recent"] = {"type": last["type"], "date": last["date"],
                             "bars_ago": bars_ago}
    return out


def trend_summary(df: pd.DataFrame, interval: str, catalysts: list[dict] | None = None
                  ) -> list[dict]:
    """추세 전환점 + 각 전환에 인접한 촉매를 묶어 반환(펼쳐보기용, 최신순)."""
    if df is None or df.empty:
        return []
    short, long = sma_windows_for(interval)
    changes = detect_trend_changes(df, short, long)
    matched = _match_catalysts(df, catalysts or [])
    # 인접 매칭 허용 범위(봉 간격 추정)
    if len(df) >= 2:
        step = (df.index[-1] - df.index[0]) / max(1, len(df) - 1)
        window = step * 6
    else:
        window = pd.Timedelta(days=10)
    rows = []
    for ch in changes:
        near = [m for m in matched if abs(pd.Timestamp(m["x"]) - pd.Timestamp(ch["date"])) <= window]
        rows.append({**ch, "catalysts": near})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows
