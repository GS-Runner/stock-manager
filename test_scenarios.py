"""시나리오/케이스 빌더 단위 테스트 — python test_scenarios.py 로 실행."""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import scenarios as SN
import storage as ST


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


def test_project_value():
    assert approx(SN.project_value(100, 0.10, 3), 133.1)     # 100*1.1^3
    assert approx(SN.project_value(100, 0.0, 5), 100.0)
    assert approx(SN.project_value(100, -1.0, 4), 0.0)       # -100% → 0
    assert approx(SN.project_value(50, 0.20, 0), 50.0)       # 0년 → 그대로
    # None/문자열 방어
    assert SN.project_value(None, "abc", 3) == 0.0
    print("  [ok] project_value 복리 투영 + 안전변환")


def test_driver_projection_eps():
    d = {"key": "EPS", "kind": "eps", "base": 2.0, "cagr": 0.15, "exit_multiple": 20}
    p = SN.driver_projection(d, 5)
    assert approx(p["future_value"], 2.0 * 1.15 ** 5, tol=1e-6)
    assert approx(p["target_price"], p["future_value"] * 20, tol=1e-6)
    assert p["implied_mcap"] is None
    print(f"  [ok] EPS 드라이버: 미래EPS={p['future_value']:.2f} → 목표가 ${p['target_price']:.1f}")


def test_driver_projection_revenue_and_custom():
    r = {"key": "Revenue", "kind": "revenue", "base": 1e9, "cagr": 0.10, "exit_multiple": 4}
    pr = SN.driver_projection(r, 3)
    assert pr["target_price"] is None
    assert approx(pr["implied_mcap"], 1e9 * 1.1 ** 3 * 4, tol=1e-3)
    c = {"key": "회원수", "kind": "custom", "base": 1e6, "cagr": 0.25, "unit": "명"}
    pc = SN.driver_projection(c, 4)
    assert pc["target_price"] is None and pc["implied_mcap"] is None
    assert approx(pc["future_value"], 1e6 * 1.25 ** 4, tol=1e-3)
    print("  [ok] Revenue(시총)/custom(참고값) 드라이버")


def test_case_valuation_upside():
    case = {"name": "Bull", "prob": 0.3, "drivers": [
        {"key": "EPS", "kind": "eps", "base": 5.0, "cagr": 0.20, "exit_multiple": 25},
    ]}
    ev = SN.case_valuation(case, years=5, price=100.0)
    fut = 5.0 * 1.2 ** 5
    tgt = fut * 25
    assert approx(ev["target_price"], tgt, tol=1e-6)
    assert approx(ev["upside"], (tgt - 100) / 100, tol=1e-6)
    assert ev["basis"] == "EPS × Fwd P/E"
    print(f"  [ok] 케이스 목표가 ${tgt:.0f}, 업사이드 {ev['upside']*100:.0f}%")


def test_case_valuation_revenue_fallback():
    """EPS 드라이버가 없으면 Revenue×P/S ÷ 주식수로 목표가 산출."""
    case = {"name": "Base", "prob": 0.5, "drivers": [
        {"key": "Revenue", "kind": "revenue", "base": 2e9, "cagr": 0.10, "exit_multiple": 5},
    ]}
    ev = SN.case_valuation(case, years=3, price=10.0, shares=1e9)
    implied_mcap = 2e9 * 1.1 ** 3 * 5
    assert approx(ev["target_price"], implied_mcap / 1e9, tol=1e-6)
    assert ev["basis"].startswith("Revenue")
    print(f"  [ok] Revenue 폴백 목표가 ${ev['target_price']:.2f}")


def test_scenario_summary_blended():
    sc = SN.default_scenario(eps0=3.0, rev0=1e9, fwd_pe=18, ps=4, shares=5e8)
    assert len(sc["cases"]) == 4
    summary = SN.scenario_summary(sc, price=50.0, shares=5e8)
    assert len(summary["cases"]) == 4
    # blended는 확률>0 & 목표가 있는 케이스의 가중평균
    tgts = [c for c in summary["cases"] if c["target_price"] is not None]
    assert tgts, "목표가 케이스 없음"
    assert summary["blended_target"] is not None
    # blended가 최소/최대 목표가 사이에 있어야 함
    lo = min(c["target_price"] for c in tgts)
    hi = max(c["target_price"] for c in tgts)
    assert lo - 1e-6 <= summary["blended_target"] <= hi + 1e-6
    print(f"  [ok] 4케이스 blended 목표가 ${summary['blended_target']:.1f} "
          f"(범위 ${lo:.0f}~${hi:.0f}), 확률합={summary['prob_sum']:.2f}")


def test_custom_driver_and_addable():
    d = SN.new_custom_driver("신용카드 결제금액", "$")
    assert d["kind"] == "custom" and d["exit_multiple"] is None
    case = {"name": "X", "prob": 0, "drivers": [d]}
    ev = SN.case_valuation(case, years=5, price=10)
    assert ev["target_price"] is None  # 커스텀만 있으면 목표가 없음(참고값만)
    assert len(ev["projections"]) == 1
    print("  [ok] 사용자지정 드라이버 추가 가능, 목표가 미산출(참고용)")


def test_storage_scenario_and_peers():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        ST.init_db(path)
        ST.add_ticker("SOFI", "SoFi", db_path=path)
        sc = SN.default_scenario(eps0=1.0, rev0=2e9, fwd_pe=20, ps=3, shares=1e9)
        sc["cases"][0]["comment"] = "침체 시나리오"
        ST.save_scenario("SOFI", sc, db_path=path)
        loaded = ST.load_scenario("SOFI", db_path=path)
        assert loaded["cases"][0]["comment"] == "침체 시나리오"
        assert len(loaded["cases"]) == 4

        ST.save_peers("SOFI", ["upst", "  ", "AFRM"], db_path=path)
        peers = ST.load_peers("SOFI", db_path=path)
        assert peers == ["UPST", "AFRM"], peers  # 정규화 + 빈값 제거

        ST.remove_ticker("SOFI", db_path=path)
        assert ST.load_scenario("SOFI", db_path=path) is None
        assert ST.load_peers("SOFI", db_path=path) == []
        print("  [ok] 시나리오/피어 저장·로드·삭제 정리")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"Running {len(tests)} tests...\n")
    failed = 0
    for t in tests:
        try:
            print(f"- {t.__name__}")
            t()
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {type(e).__name__}: {e}")
    print(f"\n{'='*50}\n{len(tests)-failed}/{len(tests)} passed"
          + (f", {failed} FAILED" if failed else " — ALL GREEN"))
    raise SystemExit(1 if failed else 0)
