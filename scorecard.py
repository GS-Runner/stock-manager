"""스코어카드 기본 템플릿 + 가중 점수 계산.

사용자의 엑셀(주식 엑셀.png)을 그대로 반영한 기본 템플릿.
가중치 합은 100. 각 항목 점수는 0~100, 사용자가 주관적으로 매긴다.
"""
from __future__ import annotations

# (category, item, ratio[%], hint)
DEFAULT_TEMPLATE: list[dict] = [
    # Valuation 33%
    {"category": "Valuation", "item": "Forward P/E", "weight": 8, "score": 0, "comment": "",
     "hint": "Forward Price earning ratio — 동종업계 대비"},
    {"category": "Valuation", "item": "CAGR (Revenue)", "weight": 8, "score": 0, "comment": "",
     "hint": "연간 매출 성장률"},
    {"category": "Valuation", "item": "CAGR (EPS)", "weight": 8, "score": 0, "comment": "",
     "hint": "연간 EPS 성장률"},
    {"category": "Valuation", "item": "PSR", "weight": 3, "score": 0, "comment": "",
     "hint": "Price to Sales"},
    {"category": "Valuation", "item": "PBR", "weight": 3, "score": 0, "comment": "",
     "hint": "Price to Book Value"},
    {"category": "Valuation", "item": "FCF or TBV", "weight": 3, "score": 0, "comment": "",
     "hint": "Free Cash Flow(기술주) / Tangible Book Value(은행주)"},
    # Risk 20%
    {"category": "Risk", "item": "부채 및 자금조달 risk", "weight": 4, "score": 0, "comment": "",
     "hint": "파산/유동성 위험"},
    {"category": "Risk", "item": "Offering risk", "weight": 4, "score": 0, "comment": "",
     "hint": "증자(신주발행) 위험"},
    {"category": "Risk", "item": "주식 희석 (SBC)", "weight": 4, "score": 0, "comment": "",
     "hint": "주식보상비용으로 인한 희석"},
    {"category": "Risk", "item": "시장 매크로 risk", "weight": 4, "score": 0, "comment": "",
     "hint": "경기침체 등 거시 위험"},
    {"category": "Risk", "item": "정책 risk", "weight": 4, "score": 0, "comment": "",
     "hint": "정부/규제 정책"},
    # Leader 12%
    {"category": "Leader", "item": "CEO 비전", "weight": 8, "score": 0, "comment": "",
     "hint": "경영진 비전/실행력"},
    {"category": "Leader", "item": "CEO 주식 보유/매수", "weight": 4, "score": 0, "comment": "",
     "hint": "내부자 보유/매수 여부"},
    # Technology 35%
    {"category": "Technology", "item": "기술 진입장벽 (혁신)", "weight": 15, "score": 0, "comment": "",
     "hint": "Moat / 진입장벽"},
    {"category": "Technology", "item": "시장 점유율 상승속도", "weight": 5, "score": 0, "comment": "",
     "hint": "점유율 확대 속도"},
    {"category": "Technology", "item": "B2B or B2C 평가", "weight": 5, "score": 0, "comment": "",
     "hint": "사업모델 평가"},
    {"category": "Technology", "item": "해당 분야 시장 성장률", "weight": 5, "score": 0, "comment": "",
     "hint": "TAM 성장률"},
    {"category": "Technology", "item": "해당 분야 시장 크기", "weight": 5, "score": 0, "comment": "",
     "hint": "TAM 규모"},
]


def default_scorecard() -> list[dict]:
    """기본 템플릿의 깊은 복사본."""
    return [dict(x) for x in DEFAULT_TEMPLATE]


# 스코어카드 항목 → Yahoo 펀더멘털 자동 매핑 (item명: (fundamentals키, 표시형식))
# 측정 가능한(객관적) 항목만. 점수(0~100)는 여전히 사용자 주관 판단.
LIVE_METRIC_MAP: dict[str, tuple[str, str]] = {
    "Forward P/E": ("forward_pe", "x"),
    "CAGR (Revenue)": ("revenue_growth", "pct"),
    "CAGR (EPS)": ("earnings_growth", "pct"),
    "PSR": ("price_to_sales", "x"),
    "PBR": ("price_to_book", "x"),
    "FCF or TBV": ("free_cashflow", "money"),
}


def _fmt_metric(v, kind: str) -> str:
    """Live 값 표시 문자열. None/오류는 빈 문자열."""
    if v is None:
        return ""
    try:
        fv = float(v)
        if fv != fv:  # NaN
            return ""
        if kind == "x":
            return f"{fv:.1f}x"
        if kind == "pct":
            return f"{fv*100:.1f}%"
        if kind == "money":
            a = abs(fv)
            for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
                if a >= div:
                    return f"${fv/div:.2f}{suf}"
            return f"${fv:,.0f}"
    except (TypeError, ValueError):
        return ""
    return str(v)


def autofill_metrics(items: list[dict], fundamentals: dict) -> list[dict]:
    """item명이 LIVE_METRIC_MAP에 있으면 'metric' 필드를 Live 실측값으로 채운다.

    파생값이므로 저장하지 않고 매 로드 시 재계산(표시는 읽기전용). 새 리스트 반환.
    """
    f = fundamentals or {}
    out = []
    for it in items:
        it = dict(it)
        m = LIVE_METRIC_MAP.get((it.get("item") or "").strip())
        it["metric"] = _fmt_metric(f.get(m[0]), m[1]) if m else it.get("metric", "")
        out.append(it)
    return out


def _f(x) -> float:
    """None/빈값/NaN/문자열을 0.0으로 안전 변환 (동적 행 추가 대응)."""
    try:
        if x is None:
            return 0.0
        v = float(x)
        return v if v == v else 0.0  # NaN → 0
    except (TypeError, ValueError):
        return 0.0


def weighted_total(items: list[dict]) -> float:
    """가중 총점 = Σ(weight × score) / Σweight. (가중치 합이 100이면 그대로 평균점)"""
    tw = sum(_f(i.get("weight")) for i in items)
    if tw <= 0:
        return 0.0
    s = sum(_f(i.get("weight")) * _f(i.get("score")) for i in items)
    return s / tw


def category_breakdown(items: list[dict]) -> dict[str, dict]:
    """카테고리별 가중치/가중점수 집계."""
    out: dict[str, dict] = {}
    for i in items:
        c = i.get("category") or "기타"
        d = out.setdefault(c, {"weight": 0.0, "weighted": 0.0})
        w = _f(i.get("weight"))
        d["weight"] += w
        d["weighted"] += w * _f(i.get("score"))
    for c, d in out.items():
        d["avg_score"] = d["weighted"] / d["weight"] if d["weight"] else 0.0
    return out


def verdict(total: float) -> tuple[str, str]:
    """사용자 매수 규칙: 70+ 매수, 60~70 소액, 60미만 보류. (label, color)"""
    if total >= 70:
        return ("매수 (BUY)", "green")
    if total >= 60:
        return ("소액 매수 (Starter)", "orange")
    return ("보류 (Hold/Pass)", "red")
