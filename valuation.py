"""Valuation engine: DCF, Reverse DCF, multiples.

순수 함수 모음 — Streamlit/네트워크에 의존하지 않으므로 단위 테스트가 쉽다.
모든 금액 단위는 호출자가 일관되게 쓰면 된다(보통 USD 절대값).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DCFAssumptions:
    fcf0: float          # 직전 12개월 잉여현금흐름(FCF), 또는 owner earnings
    growth: float        # 고성장 구간 연평균 성장률 (예: 0.15 = 15%)
    years: int           # 고성장 구간 연수
    wacc: float          # 할인율 (예: 0.10 = 10%)
    terminal_growth: float  # 영구 성장률 (예: 0.025 = 2.5%)
    net_debt: float = 0.0   # 순부채 = 총부채 - 현금 (equity value 환산용)
    shares: float = 0.0     # 발행주식수 (주당가치 환산용)


def _project_fcfs(fcf0: float, growth: float, years: int) -> list[float]:
    return [fcf0 * (1.0 + growth) ** t for t in range(1, years + 1)]


def enterprise_value(a: DCFAssumptions, growth: float | None = None) -> float:
    """주어진 가정으로 기업가치(EV, 영업가치)를 계산한다.

    growth 인자를 주면 a.growth 대신 사용한다(역DCF 풀이용).
    """
    g = a.growth if growth is None else growth
    if a.wacc <= a.terminal_growth:
        raise ValueError("WACC는 영구성장률보다 커야 합니다 (terminal value 발산).")

    fcfs = _project_fcfs(a.fcf0, g, a.years)
    pv = 0.0
    for t, fcf in enumerate(fcfs, start=1):
        pv += fcf / (1.0 + a.wacc) ** t

    fcf_terminal = fcfs[-1] * (1.0 + a.terminal_growth)
    terminal_value = fcf_terminal / (a.wacc - a.terminal_growth)
    pv += terminal_value / (1.0 + a.wacc) ** a.years
    return pv


def intrinsic_value(a: DCFAssumptions) -> dict:
    """DCF 내재가치. EV → equity value → 주당 내재가치."""
    ev = enterprise_value(a)
    equity = ev - a.net_debt
    per_share = equity / a.shares if a.shares else float("nan")
    return {
        "enterprise_value": ev,
        "equity_value": equity,
        "per_share": per_share,
    }


def reverse_dcf_implied_growth(
    a: DCFAssumptions,
    target_equity_value: float,
    lo: float = -0.50,
    hi: float = 1.00,
) -> float | None:
    """현재 시가총액(target_equity_value)을 정당화하는 '내재된 FCF 성장률'을 역산한다.

    즉 시장이 현재 가격에 기대하고 있는 성장률. 이게 현실적으로 달성 가능한지가
    핵심 판단 포인트(헤지펀드식 reverse DCF).

    풀 수 없으면(예: 음수 FCF, 범위 내 해 없음) None 반환.
    """
    if a.fcf0 <= 0:
        return None
    target_ev = target_equity_value + a.net_debt

    def f(g: float) -> float:
        return enterprise_value(a, growth=g) - target_ev

    try:
        flo, fhi = f(lo), f(hi)
    except ValueError:
        return None
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if flo * fhi > 0:
        return None  # 범위 내 부호변화 없음 → 해 없음

    # 이분법 (scipy 없이도 동작하도록 자체 구현)
    for _ in range(200):
        mid = (lo + hi) / 2.0
        fmid = f(mid)
        if abs(fmid) < 1.0 or (hi - lo) < 1e-9:
            return mid
        if flo * fmid < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return (lo + hi) / 2.0


def forward_multiples(price: float, eps0: float, growth: float, years: int) -> list[dict]:
    """현재가 기준 향후 N년 Forward P/E를 EPS 성장가정으로 투영한다."""
    out = []
    for t in range(0, years + 1):
        eps_t = eps0 * (1.0 + growth) ** t
        pe = price / eps_t if eps_t > 0 else float("nan")
        out.append({"year_offset": t, "eps": eps_t, "forward_pe": pe})
    return out


def margin_of_safety(intrinsic_per_share: float, price: float) -> float | None:
    """안전마진 = (내재가치 - 현재가) / 내재가치. 양수면 저평가."""
    if not intrinsic_per_share or intrinsic_per_share != intrinsic_per_share:  # NaN
        return None
    if intrinsic_per_share <= 0:
        return None
    return (intrinsic_per_share - price) / intrinsic_per_share
