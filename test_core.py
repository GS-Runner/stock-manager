"""핵심 로직 단위 테스트 — pytest 없이 python test_core.py 로 실행."""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글/유니코드 출력
except Exception:
    pass

import valuation as V
import scorecard as SC
import storage as ST
import scenarios as SN
import export as EXP


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


def test_dcf_roundtrip():
    """역DCF로 구한 성장률을 다시 정DCF에 넣으면 목표 시총이 복원돼야 한다."""
    a = V.DCFAssumptions(fcf0=1000.0, growth=0.10, years=10, wacc=0.10,
                         terminal_growth=0.025, net_debt=0.0, shares=100.0)
    target = a.equity_value if hasattr(a, "equity_value") else None
    ev = V.enterprise_value(a)
    equity = ev  # net_debt=0
    g = V.reverse_dcf_implied_growth(a, equity)
    assert g is not None, "성장률 풀이 실패"
    assert approx(g, 0.10, tol=1e-3), f"역산 성장률 {g} != 0.10"
    print(f"  [ok] reverse DCF implied growth = {g:.4%} (기대 10%)")


def test_dcf_monotonic():
    """성장률↑ → 기업가치↑ (단조 증가)."""
    base = V.DCFAssumptions(fcf0=500, growth=0.05, years=8, wacc=0.09, terminal_growth=0.02)
    lo = V.enterprise_value(base, growth=0.03)
    hi = V.enterprise_value(base, growth=0.12)
    assert hi > lo, "성장률 증가 시 가치가 증가해야 함"
    print(f"  [ok] EV(g=3%)={lo:,.0f} < EV(g=12%)={hi:,.0f}")


def test_dcf_invalid_wacc():
    a = V.DCFAssumptions(fcf0=100, growth=0.05, years=5, wacc=0.02, terminal_growth=0.03)
    try:
        V.enterprise_value(a)
        assert False, "WACC<=g_term 인데 예외가 없음"
    except ValueError:
        print("  [ok] WACC<=terminal_growth 에서 ValueError 발생")


def test_reverse_dcf_negative_fcf():
    a = V.DCFAssumptions(fcf0=-50, growth=0.1, years=5, wacc=0.1, terminal_growth=0.02)
    assert V.reverse_dcf_implied_growth(a, 1000) is None
    print("  [ok] 음수 FCF → None 반환")


def test_intrinsic_and_mos():
    a = V.DCFAssumptions(fcf0=1000, growth=0.08, years=10, wacc=0.09,
                         terminal_growth=0.025, net_debt=2000, shares=1000)
    iv = V.intrinsic_value(a)
    assert iv["equity_value"] == iv["enterprise_value"] - 2000
    mos = V.margin_of_safety(iv["per_share"], iv["per_share"] * 0.8)
    assert approx(mos, 0.2, tol=1e-6), mos
    print(f"  [ok] 주당 내재가치={iv['per_share']:.2f}, 안전마진(20%할인가)={mos:.2%}")


def test_forward_multiples():
    rows = V.forward_multiples(price=100, eps0=5, growth=0.2, years=3)
    assert approx(rows[0]["forward_pe"], 20.0)      # 100/5
    assert rows[3]["eps"] > rows[0]["eps"]
    assert rows[3]["forward_pe"] < rows[0]["forward_pe"]  # EPS 성장 → PE 하락
    print(f"  [ok] forward P/E: now={rows[0]['forward_pe']:.1f} → +3y={rows[3]['forward_pe']:.1f}")


def test_scorecard_total():
    items = SC.default_scorecard()
    assert approx(sum(i["weight"] for i in items), 100.0), "가중치 합 != 100"
    for i in items:
        i["score"] = 80
    assert approx(SC.weighted_total(items), 80.0)
    print("  [ok] 가중치 합=100, 전부 80점 → 총점 80.0")


def test_scorecard_example():
    """엑셀 예시(SOFI 77.4)와 유사 구조 검증 — 카테고리 집계."""
    items = SC.default_scorecard()
    bd = SC.category_breakdown(items)
    assert set(bd) == {"Valuation", "Risk", "Leader", "Technology"}
    assert approx(bd["Valuation"]["weight"], 33)
    assert approx(bd["Technology"]["weight"], 35)
    print(f"  [ok] 카테고리 가중치: " +
          ", ".join(f"{k}={v['weight']:.0f}%" for k, v in bd.items()))


def test_scorecard_empty_rows():
    """동적 행 추가로 None/빈 값이 섞여도 크래시하지 않아야 한다(회귀)."""
    items = SC.default_scorecard()
    items.append({"category": None, "item": "", "weight": None, "score": None, "comment": ""})
    items.append({"category": "x", "item": "y", "weight": "", "score": "abc"})
    t = SC.weighted_total(items)        # 예외 없이 계산돼야
    bd = SC.category_breakdown(items)   # 예외 없이 집계돼야
    assert 0 <= t <= 100, t
    assert "기타" in bd  # category None → '기타'
    print(f"  [ok] 빈/None 행 혼합에도 총점 계산={t:.1f}, 크래시 없음")


def test_scorecard_autofill():
    """Live 펀더멘털로 측정가능 항목(PER/PSR/PBR/CAGR/FCF)의 실측값 자동 채움."""
    items = SC.default_scorecard()
    f = {"forward_pe": 12.3, "revenue_growth": 0.25, "earnings_growth": 0.40,
         "price_to_sales": 3.1, "price_to_book": 1.8, "free_cashflow": 2.5e9}
    filled = SC.autofill_metrics(items, f)
    by = {i["item"]: i.get("metric") for i in filled}
    assert by["Forward P/E"] == "12.3x", by["Forward P/E"]
    assert by["CAGR (Revenue)"] == "25.0%", by["CAGR (Revenue)"]
    assert by["FCF or TBV"] == "$2.50B", by["FCF or TBV"]
    # 매핑 없는 주관 항목은 빈 실측값
    assert by["CEO 비전"] == ""
    # None/NaN 방어
    filled2 = SC.autofill_metrics(items, {"forward_pe": None})
    assert {i["item"]: i.get("metric") for i in filled2}["Forward P/E"] == ""
    print("  [ok] 스코어카드 Live 자동 채움 (PER/CAGR/FCF), None 방어")


def test_verdict():
    assert SC.verdict(75)[0].startswith("매수")
    assert SC.verdict(65)[0].startswith("소액")
    assert SC.verdict(55)[0].startswith("보류")
    print("  [ok] verdict: 75→매수, 65→소액, 55→보류")


def test_storage_crud():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        ST.init_db(path)
        ST.add_ticker("sofi", "SoFi Technologies", "long", db_path=path)
        ST.add_ticker("AAPL", "Apple", "swing", db_path=path)
        tks = ST.list_tickers(path)
        assert len(tks) == 2
        assert any(t["symbol"] == "SOFI" for t in tks)

        items = SC.default_scorecard()
        items[0]["score"] = 90
        ST.save_scorecard("SOFI", items, db_path=path)
        loaded = ST.load_scorecard("SOFI", db_path=path)
        assert loaded[0]["score"] == 90

        ST.add_trade("SOFI", "2025-06-28", "BUY", 18.0, 100, "테스트", db_path=path)
        ST.add_trade("SOFI", "2025-06-29", "BUY", 20.0, 100, "추가", db_path=path)
        pos = ST.position_summary("SOFI", path)
        assert pos["shares"] == 200
        assert approx(pos["avg_price"], 19.0), pos
        ST.add_trade("SOFI", "2025-06-30", "SELL", 25.0, 50, "일부익절", db_path=path)
        pos2 = ST.position_summary("SOFI", path)
        assert pos2["shares"] == 150, pos2

        ST.add_catalyst("SOFI", "2025-06-27", "악재", "공매도 증가", 18.0, -5, 60, "", db_path=path)
        assert len(ST.list_catalysts("SOFI", path)) == 1

        ST.save_assumptions("SOFI", {"wacc": 0.1, "growth": 0.2}, db_path=path)
        assert ST.load_assumptions("SOFI", path)["wacc"] == 0.1

        ST.remove_ticker("AAPL", db_path=path)
        assert len(ST.list_tickers(path)) == 1
        print("  [ok] storage CRUD: tickers/scorecard/trades/positions/catalysts/assumptions")
    finally:
        os.unlink(path)


def test_user_isolation_and_backup():
    """사용자별 DB 격리 + 백업/복원 검증."""
    import os
    a = ST.user_db_path("alice::pw1")
    b = ST.user_db_path("bob::pw2")
    a2 = ST.user_db_path("ALICE::pw1")  # 대소문자 무시 → alice와 동일
    assert a != b, "다른 사용자가 같은 DB를 공유함"
    assert a == a2, "같은 사용자가 다른 DB로 분리됨"

    ST.init_db(a)
    ST.init_db(b)
    ST.add_ticker("AAA", "A", db_path=a)
    ST.add_ticker("BBB", "B", db_path=b)
    assert [t["symbol"] for t in ST.list_tickers(a)] == ["AAA"]
    assert [t["symbol"] for t in ST.list_tickers(b)] == ["BBB"], "데이터가 섞임!"

    # 백업/복원
    blob = ST.export_db_bytes(a)
    assert blob[:16].startswith(b"SQLite format 3")
    assert ST.import_db_bytes(b, blob) is True       # b를 a의 백업으로 덮어씀
    assert [t["symbol"] for t in ST.list_tickers(b)] == ["AAA"], "복원 실패"
    assert ST.import_db_bytes(b, b"garbage") is False  # 잘못된 파일 거부
    for p in (a, b):
        try:
            os.unlink(p)
        except OSError:
            pass
    print("  [ok] 사용자별 DB 격리, 백업/복원, 손상파일 거부")


def test_auth():
    """계정 생성/검증 — scrypt 해시, 이름 중복 방지, 오답 비밀번호 거부."""
    import tempfile
    orig_auth = ST.AUTH_DB_PATH
    fd, ST.AUTH_DB_PATH = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        assert ST.user_exists("neo") is False
        assert ST.create_user("neo", "matrix123") is True
        assert ST.create_user("neo", "다른비번") is False, "중복 이름 생성 방지 실패"
        assert ST.user_exists("neo") is True
        assert ST.verify_password("neo", "matrix123") is True
        assert ST.verify_password("neo", "wrong") is False
        assert ST.verify_password("nobody", "x") is False
        print("  [ok] 계정 생성/중복방지/비밀번호 검증(scrypt)")
    finally:
        try:
            os.unlink(ST.AUTH_DB_PATH)
        except OSError:
            pass
        ST.AUTH_DB_PATH = orig_auth


def test_pg_wrapper_placeholder_translation():
    """Postgres 어댑터(_PGCursorWrapper) — sqlite `?` 플레이스홀더를 psycopg2 `%s`로
    올바르게 치환하는지, 실제 DB 연결 없이 mock 커서로 검증."""
    class _FakeCursor:
        def __init__(self):
            self.calls = []
        def execute(self, sql, params):
            self.calls.append((sql, params))

    class _FakeConn:
        def __init__(self):
            self.cursor_obj = _FakeCursor()
        def cursor(self):
            return self.cursor_obj

    fake_con = _FakeConn()
    wrapper = ST._PGCursorWrapper(fake_con)
    wrapper.execute("SELECT * FROM tickers WHERE symbol=? AND kind=?", ("AAPL", "long"))
    sql, params = fake_con.cursor_obj.calls[0]
    assert sql == "SELECT * FROM tickers WHERE symbol=%s AND kind=%s", sql
    assert params == ("AAPL", "long")
    print("  [ok] PG 어댑터 플레이스홀더(?→%s) 치환 정상")


def test_pg_schema_name_stable():
    """동일 시드는 항상 동일 스키마명, 다른 시드는 다른 스키마명(사용자 격리)."""
    a1 = ST._schema_name("alice::pw1")
    a2 = ST._schema_name("alice::pw1")
    b = ST._schema_name("bob::pw2")
    assert a1 == a2 and a1 != b
    assert a1.startswith("u_") and len(a1) == len("u_") + 16
    print(f"  [ok] PG 스키마명 안정적 생성: {a1} != {b}")


def test_excel_export():
    """엑셀 내보내기: 유효한 .xlsx 바이트 생성 + 시트 왕복 검증."""
    import io
    import pandas as pd
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        ST.init_db(path)
        ST.add_ticker("SOFI", "SoFi", "long", db_path=path)
        items = SC.default_scorecard()
        items[0]["score"] = 88
        ST.save_scorecard("SOFI", items, db_path=path)
        ST.add_trade("SOFI", "2025-06-28", "BUY", 18.0, 100, "진입", db_path=path)
        ST.add_catalyst("SOFI", "2025-06-27", "호재", "실적 서프라이즈", 18.0, 5, 40, "",
                        db_path=path)
        ST.save_scenario("SOFI", SN.default_scenario(eps0=1.0, rev0=2e9, fwd_pe=20,
                                                     ps=3, shares=1e9), db_path=path)
        blob = EXP.export_excel_bytes(path)
        assert blob[:2] == b"PK", "xlsx(zip) 시그니처 아님"
        sheets = pd.read_excel(io.BytesIO(blob), sheet_name=None)
        assert {"워치리스트", "스코어카드", "촉매", "매매기록", "시나리오"} <= set(sheets)
        assert (sheets["스코어카드"]["점수"] == 88).any(), "스코어카드 값 누락"
        assert len(sheets["시나리오"]) >= 4, "시나리오 행 누락"
        print(f"  [ok] 엑셀 내보내기: 시트 {list(sheets)} 왕복 검증")
    finally:
        os.unlink(path)


def test_excel_export_empty():
    """데이터가 없어도 안내 시트로 크래시 없이 생성돼야 한다."""
    import io
    import pandas as pd
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        ST.init_db(path)
        blob = EXP.export_excel_bytes(path)
        sheets = pd.read_excel(io.BytesIO(blob), sheet_name=None)
        assert "워치리스트" in sheets
        print("  [ok] 빈 DB도 엑셀 생성(안내 시트)")
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
