"""기록 엑셀(.xlsx) 내보내기 — 워치리스트/스코어카드/촉매/매매/시나리오를 시트로 저장.

pandas + openpyxl 사용. Streamlit 비의존(테스트 용이). 저장소 데이터를 읽기만 한다.
"""
from __future__ import annotations

import io

import pandas as pd

import scenarios as SN
import storage as ST


def _write(xl, name: str, rows: list[dict], placeholder: str) -> None:
    """rows가 있으면 그대로, 없으면 안내 문구 한 줄로 시트 생성."""
    df = pd.DataFrame(rows) if rows else pd.DataFrame([{"안내": placeholder}])
    df.to_excel(xl, sheet_name=name, index=False)


def export_excel_bytes(db_path: str) -> bytes:
    """현재 사용자 DB 전체를 여러 시트의 .xlsx 바이트로 반환."""
    tickers = ST.list_tickers(db_path)

    watch = [{"티커": t["symbol"], "이름": t.get("name"),
              "분류": "장기" if t.get("kind") == "long" else "스윙",
              "추가일": t.get("added_at")} for t in tickers]

    sc_rows, cat_rows, trade_rows, scn_rows = [], [], [], []
    for t in tickers:
        sym = t["symbol"]
        card = ST.load_scorecard(sym, db_path)
        if card:
            for it in card:
                sc_rows.append({"티커": sym, "카테고리": it.get("category"),
                                "항목": it.get("item"), "가중치%": it.get("weight"),
                                "점수": it.get("score"), "코멘트": it.get("comment")})
        for c in ST.list_catalysts(sym, db_path):
            cat_rows.append({"티커": sym, "날짜": c.get("date"), "구분": c.get("kind"),
                             "헤드라인": c.get("headline"), "당시가": c.get("price_at"),
                             "기대영향%": c.get("expected_impact"),
                             "반영도%": c.get("reflected_pct"), "메모": c.get("note")})
        for tr in ST.list_trades(sym, db_path):
            trade_rows.append({"티커": sym, "날짜": tr.get("date"),
                               "구분": tr.get("action"), "체결가": tr.get("price"),
                               "수량": tr.get("shares"), "근거": tr.get("reason")})
        scn = ST.load_scenario(sym, db_path)
        if scn:
            years = scn.get("horizon_years")
            for case in scn.get("cases", []):
                for d in case.get("drivers", []):
                    scn_rows.append({
                        "티커": sym, "케이스": case.get("name"),
                        "확률": case.get("prob"), "연수": years,
                        "지표": d.get("key"), "종류": d.get("kind"),
                        "기준값": d.get("base"),
                        "CAGR%": round(SN._f(d.get("cagr")) * 100, 1),
                        "exit배수": d.get("exit_multiple"),
                        "케이스코멘트": case.get("comment")})

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        _write(xl, "워치리스트", watch, "등록된 종목이 없습니다.")
        _write(xl, "스코어카드", sc_rows, "저장된 스코어카드가 없습니다.")
        _write(xl, "촉매", cat_rows, "기록된 촉매가 없습니다.")
        _write(xl, "매매기록", trade_rows, "매매 기록이 없습니다.")
        _write(xl, "시나리오", scn_rows, "저장된 시나리오가 없습니다.")
    return buf.getvalue()
