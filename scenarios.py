"""시나리오/케이스 밸류에이션 — Bear/Base/Bull/Super Bull 등 다중 가정 관리.

각 케이스는 여러 '드라이버'(EPS, Revenue, 사용자지정 지표: 회원수·계약건수·판매량 등)를
갖는다. 각 드라이버는 기준값(base)과 연평균성장률(CAGR)로 N년 후 값을 투영한다.
EPS/Revenue처럼 exit 멀티플이 있으면 목표주가·업사이드를 계산한다.

순수 함수 — Streamlit/네트워크에 비의존하므로 단위 테스트가 쉽다.
"""
from __future__ import annotations

# 케이스 기본 프리셋 (이름, 색, 기본 EPS CAGR, 기본 확률). 사용자가 자유롭게 수정.
CASE_PRESETS = [
    {"name": "Bear", "color": "red", "eps_cagr": -0.05, "prob": 0.20},
    {"name": "Base", "color": "orange", "eps_cagr": 0.10, "prob": 0.40},
    {"name": "Bull", "color": "green", "eps_cagr": 0.20, "prob": 0.30},
    {"name": "Super Bull", "color": "violet", "eps_cagr": 0.35, "prob": 0.10},
]


def _f(x, default: float = 0.0) -> float:
    """None/빈값/NaN/문자열을 안전하게 float로 (동적 입력 대응)."""
    try:
        if x is None or x == "":
            return default
        v = float(x)
        return v if v == v else default  # NaN 방어
    except (TypeError, ValueError):
        return default


def project_value(base: float, cagr: float, years: int) -> float:
    """기준값을 CAGR로 N년 복리 투영. base*(1+cagr)^years."""
    base = _f(base)
    cagr = _f(cagr)
    years = max(0, int(years))
    return base * (1.0 + cagr) ** years


def driver_projection(driver: dict, years: int) -> dict:
    """단일 드라이버의 N년 후 값. exit 멀티플이 있으면 목표주가/시총도 계산.

    - kind='eps'     : target_price = 미래 EPS × exit_multiple(=Forward P/E)
    - kind='revenue' : implied_mcap = 미래 매출 × exit_multiple(=P/S). 주당은 상위에서 shares로 환산.
    - kind='custom'  : 참고용 투영값만(회원수/계약건수/판매량 등).
    """
    base = _f(driver.get("base"))
    cagr = _f(driver.get("cagr"))
    fut = project_value(base, cagr, years)
    mult = driver.get("exit_multiple")
    kind = driver.get("kind", "custom")
    out = {
        "key": driver.get("key", ""),
        "kind": kind,
        "base": base,
        "cagr": cagr,
        "future_value": fut,
        "unit": driver.get("unit", ""),
        "target_price": None,   # per-share (eps 기준)
        "implied_mcap": None,   # revenue 기준
    }
    m = _f(mult, default=0.0)
    if kind == "eps" and m > 0:
        out["target_price"] = fut * m
    elif kind == "revenue" and m > 0:
        out["implied_mcap"] = fut * m
    return out


def case_valuation(case: dict, years: int, price: float | None = None,
                   shares: float | None = None) -> dict:
    """한 케이스의 드라이버들을 투영하고 케이스 목표주가/업사이드를 산출.

    목표주가 우선순위: EPS 기반(있으면) → 없으면 Revenue 기반(shares 필요).
    """
    drivers = case.get("drivers", []) or []
    projs = [driver_projection(d, years) for d in drivers]

    target = None
    basis = None
    # 1순위: EPS 드라이버
    for p in projs:
        if p["kind"] == "eps" and p["target_price"] is not None:
            target = p["target_price"]
            basis = "EPS × Fwd P/E"
            break
    # 2순위: Revenue 드라이버 (shares로 주당 환산)
    if target is None and shares and shares > 0:
        for p in projs:
            if p["kind"] == "revenue" and p["implied_mcap"] is not None:
                target = p["implied_mcap"] / shares
                basis = "Revenue × P/S ÷ 주식수"
                break

    upside = None
    if target is not None and price:
        p = _f(price)
        if p > 0:
            upside = (target - p) / p

    return {
        "name": case.get("name", ""),
        "color": case.get("color", "gray"),
        "prob": _f(case.get("prob"), default=0.0),
        "comment": case.get("comment", ""),
        "projections": projs,
        "target_price": target,
        "basis": basis,
        "upside": upside,
    }


def scenario_summary(scenario: dict, price: float | None = None,
                     shares: float | None = None) -> dict:
    """전체 시나리오(모든 케이스) 요약 + 확률가중 기대 목표주가(blended)."""
    years = max(1, int(_f(scenario.get("horizon_years"), default=5)))
    cases = scenario.get("cases", []) or []
    evals = [case_valuation(c, years, price, shares) for c in cases]

    # 확률 가중 기대 목표주가 — 목표주가가 있는 케이스만, 확률 합으로 정규화.
    weighted, wsum = 0.0, 0.0
    for e in evals:
        if e["target_price"] is not None and e["prob"] > 0:
            weighted += e["target_price"] * e["prob"]
            wsum += e["prob"]
    blended = (weighted / wsum) if wsum > 0 else None
    blended_upside = None
    if blended is not None and price and _f(price) > 0:
        blended_upside = (blended - _f(price)) / _f(price)

    return {
        "years": years,
        "cases": evals,
        "blended_target": blended,
        "blended_upside": blended_upside,
        "prob_sum": sum(e["prob"] for e in evals),
    }


def default_scenario(eps0: float | None = None, rev0: float | None = None,
                     fwd_pe: float | None = None, ps: float | None = None,
                     shares: float | None = None) -> dict:
    """Live 지표로 4개 기본 케이스(Bear/Base/Bull/Super Bull) 초안 생성.

    exit 멀티플은 현재 Forward P/E / PSR을 기본값으로 두되, 없으면 관용적 기본값.
    """
    eps0 = _f(eps0, default=1.0) or 1.0
    rev0 = _f(rev0, default=0.0)
    pe = _f(fwd_pe, default=0.0)
    base_pe = pe if pe > 0 else 20.0
    base_ps = _f(ps, default=0.0)
    cases = []
    for preset in CASE_PRESETS:
        g = preset["eps_cagr"]
        # 케이스가 낙관적일수록 시장이 부여하는 exit 멀티플도 소폭 확장/축소한다고 가정.
        mult_adj = 1.0 + g  # Bear면 축소, Bull이면 확장
        drivers = [
            {"key": "EPS", "kind": "eps", "base": round(eps0, 4), "cagr": g,
             "unit": "$", "exit_multiple": round(base_pe * mult_adj, 1)},
        ]
        if rev0 > 0:
            drivers.append(
                {"key": "Revenue", "kind": "revenue", "base": rev0,
                 "cagr": max(0.0, g + 0.05), "unit": "$",
                 "exit_multiple": round(base_ps, 2) if base_ps > 0 else 3.0})
        cases.append({
            "name": preset["name"], "color": preset["color"],
            "prob": preset["prob"], "comment": "", "drivers": drivers,
        })
    return {"horizon_years": 5, "cases": cases}


def new_custom_driver(key: str = "새 지표", unit: str = "") -> dict:
    """사용자지정 드라이버 템플릿(회원수·계약건수·판매량·결제금액 등)."""
    return {"key": key, "kind": "custom", "base": 0.0, "cagr": 0.0,
            "unit": unit, "exit_multiple": None}
