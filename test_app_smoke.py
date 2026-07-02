"""AppTest로 실제 스크립트 실행 — 렌더링 중 예외가 없는지 검증.
streamlit.testing 이 in-process로 app.py를 실행한다(브라우저 불필요)."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import tempfile
from streamlit.testing.v1 import AppTest
import storage as ST

# 테스트용 격리 DB 시드 (사용자 게이트 우회: session_state에 db_path 주입)
_fd, _DB = tempfile.mkstemp(suffix=".db")
os.close(_fd)
ST.init_db(_DB)
ST.add_ticker("AAPL", "Apple Inc.", "long", db_path=_DB)

print("0) 사용자 게이트(미인증) 화면 확인...")
gate = AppTest.from_file("app.py").run(timeout=30)
assert not gate.exception, f"게이트 예외: {gate.exception}"
assert gate.text_input, "게이트에 로그인/회원가입 입력이 없음"
assert len(gate.tabs) == 2, f"게이트 탭(로그인/회원가입) 구성이 다름: {len(gate.tabs)}"
assert not gate.sidebar.radio, "미인증인데 페이지 네비게이션(사이드바)이 노출됨(격리 실패)"
assert not gate.metric, "미인증인데 본문 metric이 노출됨(격리 실패)"
print("   [ok] 미인증 시 로그인/회원가입 게이트만 노출, 본문 차단됨")

print("0.5) 회원가입 → 오답 비밀번호 거부 → 정답 로그인 → 기존 데이터 유지 확인...")
_orig_auth_db = ST.AUTH_DB_PATH
_afd, ST.AUTH_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_afd)
_flow_db_path = None
try:
    gate2 = AppTest.from_file("app.py").run(timeout=30)
    gate2.text_input(key="su_name").set_value("flow_tester")
    gate2.text_input(key="su_pw").set_value("pw1234")
    gate2.text_input(key="su_pw2").set_value("pw1234")
    gate2.button(key="FormSubmitter:signup_form-계정 만들기 →").click().run(timeout=30)
    assert not gate2.exception, f"회원가입 예외: {gate2.exception}"
    assert "db_path" in gate2.session_state, "회원가입 후 세션에 db_path가 없음"
    _flow_db_path = gate2.session_state["db_path"]
    ST.add_ticker("NVDA", "NVIDIA Corp.", "long", db_path=_flow_db_path)

    gate3 = AppTest.from_file("app.py").run(timeout=30)
    gate3.text_input(key="li_name").set_value("flow_tester")
    gate3.text_input(key="li_pw").set_value("wrongpw")
    gate3.button(key="FormSubmitter:login_form-로그인 →").click().run(timeout=30)
    assert not gate3.exception, f"오답 로그인 예외: {gate3.exception}"
    assert "db_path" not in gate3.session_state, "오답 비밀번호인데 로그인이 통과됨"
    assert gate3.error, "오답 비밀번호에 에러 메시지가 없음"

    gate4 = AppTest.from_file("app.py").run(timeout=30)
    gate4.text_input(key="li_name").set_value("flow_tester")
    gate4.text_input(key="li_pw").set_value("pw1234")
    gate4.button(key="FormSubmitter:login_form-로그인 →").click().run(timeout=30)
    assert not gate4.exception, f"정답 로그인 예외: {gate4.exception}"
    assert "db_path" in gate4.session_state, "정답 비밀번호인데 로그인이 실패함"
    assert [t["symbol"] for t in ST.list_tickers(gate4.session_state["db_path"])] == ["NVDA"], \
        "재로그인 후 기존 데이터가 보이지 않음"
    print("   [ok] 회원가입/오답거부/재로그인 시 데이터 유지 — 전부 정상")
finally:
    try:
        os.unlink(ST.AUTH_DB_PATH)
    except OSError:
        pass
    if _flow_db_path:
        try:
            os.unlink(_flow_db_path)
        except OSError:
            pass
    ST.AUTH_DB_PATH = _orig_auth_db

print("1) 대시보드 페이지 실행 (인증 우회)...")
at = AppTest.from_file("app.py")
at.session_state["db_path"] = _DB
at.session_state["user_name"] = "tester"
at.run(timeout=60)
assert not at.exception, f"대시보드 예외: {at.exception}"
print("   [ok] 대시보드 예외 없음. title:", at.title[0].value if at.title else "—")

print("1.5) 대시보드 종목 행 클릭 → 상세 이동 시뮬레이션...")
# AppTest는 dataframe 행선택을 직접 못 하므로, 앱이 설정하는 플래그를 주입해
# page_nav 위젯 생성 전 처리 로직(_nav_detail/_goto_symbol)이 동작하는지 검증한다.
at.session_state["_goto_symbol"] = "AAPL"
at.session_state["_nav_detail"] = True
at.run(timeout=120)
assert not at.exception, f"행클릭 이동 예외: {at.exception}"
assert at.session_state["page_nav"] == "🔍 종목 상세", "행 클릭이 상세 페이지로 전환 안 됨"
assert at.session_state["detail_sel"] == "AAPL", "선택 종목이 상세에 반영 안 됨"
assert "_nav_detail" not in at.session_state, "_nav_detail 플래그가 소비되지 않음(무한 이동 위험)"
print("   [ok] 행 클릭 → page_nav=상세, detail_sel=AAPL, 플래그 소비됨")

print("2) 종목 상세 페이지로 전환 후 실행...")
# 페이지 라디오(key=page_nav)를 '종목 상세'로 변경 — 모든 탭 본문이 실행된다
at.radio(key="page_nav").set_value("🔍 종목 상세").run(timeout=120)
assert not at.exception, f"상세 페이지 예외: {at.exception}"
assert len(at.tabs) >= 7, f"탭이 렌더되지 않음 (탭 수={len(at.tabs)}) — 상세 페이지 미실행"
labels = [m.label for m in at.metric]
assert "Forward P/E" in labels, f"개요 탭 metric 미렌더: {labels[:10]}"
assert "주당 내재가치" in labels, "DCF 탭 미렌더"
assert "확률가중 기대 목표주가" in labels, f"시나리오 탭 미렌더: {labels[:20]}"
assert "뉴스 버즈" in labels and "헤드라인 톤" in labels and "애널리스트 모멘텀" in labels, \
    f"뉴스·Narrative 탭 미렌더: {labels[:20]}"
print(f"   [ok] 상세 페이지 예외 없음. 탭 {len(at.tabs)}개, metric {len(at.metric)}개 렌더")
print(f"   주요 metric 일부: {[l for l in labels if l in ('Forward P/E','P/B','P/S','EV/EBITDA','주당 내재가치','내재 FCF 성장률')]}")

print("3) 차트: 일봉(캔들)+실시간 ON(다이나믹 TradingView 기본값), 월봉 경로 실행...")
assert at.segmented_control, "차트 컨트롤(segmented_control) 미렌더"
sym = at.segmented_control[0].key.replace("gran_", "")
assert at.toggle(key=f"dyn_{sym}").value is True, "다이나믹(TradingView) 차트 기본값이 ON이 아님"
at.segmented_control(key=f"gran_{sym}").set_value("일봉")
at.toggle(key=f"live_{sym}").set_value(True)
at.run(timeout=120)
assert not at.exception, f"일봉/실시간(다이나믹) 예외: {at.exception}"
at.segmented_control(key=f"gran_{sym}").set_value("월봉")
at.toggle(key=f"live_{sym}").set_value(False)
at.run(timeout=120)
assert not at.exception, f"월봉(다이나믹) 예외: {at.exception}"
print(f"   [ok] {sym} 일봉+실시간 / 월봉 렌더 예외 없음 (TradingView 컴포넌트)")

print("3.5) 다이나믹 OFF → 기존 plotly 폴백 차트 경로 실행...")
at.toggle(key=f"dyn_{sym}").set_value(False)
at.run(timeout=120)
assert not at.exception, f"plotly 폴백 예외: {at.exception}"
print("   [ok] 다이나믹 OFF 시 plotly 차트 렌더 예외 없음")

print("4) 스캐너 페이지 실행...")
at.radio(key="page_nav").set_value("🔎 스캐너").run(timeout=120)
assert not at.exception, f"스캐너 예외: {at.exception}"
assert any("스캐너" in (tt.value or "") for tt in at.title), "스캐너 타이틀 미렌더"
print("   [ok] 스캐너 페이지 예외 없음")

try:
    os.unlink(_DB)
except OSError:
    pass

print("\n==================================================")
print("APP SMOKE TEST PASSED — 렌더링 예외 없음")
