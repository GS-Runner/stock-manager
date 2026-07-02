"""영속 저장소. 워치리스트, 스코어카드, 촉매(뉴스) 로그, 매매 기록, DCF 가정.

기본은 stdlib sqlite3(사용자별 파일 격리). `DATABASE_URL`이 설정되면(무료 Neon Postgres
등) 자동으로 Postgres 백엔드로 전환된다 — 클라우드 재배포에도 데이터가 휘발되지 않는다.
Postgres에서는 파일 대신 사용자별 스키마(schema)로 격리하므로, `db_path` 인자는 두 백엔드
모두에서 "사용자 데이터 격리 키"라는 동일한 의미로 쓰인다(호출부/함수 시그니처 불변).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # 로컬 개발/테스트 환경엔 없어도 됨(SQLite로 폴백)
    psycopg2 = None

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.db")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
AUTH_DB_PATH = os.path.join(DATA_DIR, "_auth.db")

# app.py가 st.secrets["DATABASE_URL"]을 읽어 여기 주입한다(storage.py는 streamlit에
# 의존하지 않도록 유지 — 테스트에서 단독 import 가능해야 함). 환경변수도 폴백으로 지원.
DATABASE_URL: str | None = os.environ.get("DATABASE_URL")


def _use_pg() -> bool:
    return bool(DATABASE_URL) and psycopg2 is not None


def user_db_path(user_id: str) -> str:
    """사용자별 격리 키. user_id(이름+비번)를 해시해 만든다.
    SQLite 백엔드: 이 값 자체가 DB 파일 경로. Postgres 백엔드: 스키마명 시드로 재사용됨."""
    os.makedirs(DATA_DIR, exist_ok=True)
    safe = hashlib.sha256(user_id.strip().lower().encode("utf-8")).hexdigest()[:16]
    return os.path.join(DATA_DIR, f"portfolio_{safe}.db")


def _schema_name(seed: str) -> str:
    """Postgres 스키마명(사용자 격리 단위). seed는 user_db_path()가 만든 문자열(파일경로
    형태)이든 임의 문자열이든 상관없이 안정적인 식별자를 만든다."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"u_{h}"


class _PGCursorWrapper:
    """sqlite3.Connection.execute()와 동일한 호출 형태(`?` 플레이스홀더)를 psycopg2에서도
    쓸 수 있게 하는 얇은 어댑터. 이 코드베이스의 SQL 문자열엔 리터럴 '?'가 없어 안전하게
    치환 가능(검증됨)."""

    def __init__(self, con):
        self._con = con

    def execute(self, sql: str, params: tuple = ()):
        cur = self._con.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def executescript(self, script: str):
        cur = self._con.cursor()
        cur.execute(script)
        return cur


def export_db_bytes(db_path: str) -> bytes:
    """백업용 — DB 파일 전체를 바이트로 반환(없으면 빈 바이트).
    Postgres 백엔드에선 파일 자체가 없으므로 사용 불가(Postgres는 이미 영구 저장이라
    파일 백업이 불필요 — 대신 엑셀 내보내기(export.py)를 데이터 열람용으로 쓴다)."""
    if _use_pg() or not os.path.exists(db_path):
        return b""
    with open(db_path, "rb") as fh:
        return fh.read()


def import_db_bytes(db_path: str, data: bytes) -> bool:
    """복원용 — 업로드된 SQLite 파일로 교체. 헤더 검증 후 기록. 성공 시 True.
    Postgres 백엔드에선 지원 안 함(위 export_db_bytes 설명 참고)."""
    if _use_pg() or not data or not data[:16].startswith(b"SQLite format 3"):
        return False
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, "wb") as fh:
        fh.write(data)
    return True


@contextmanager
def _conn(db_path: str = DB_PATH):
    if _use_pg():
        con = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        schema = _schema_name(db_path)
        try:
            with con.cursor() as cur:
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                cur.execute(f'SET search_path TO "{schema}", public')
            yield _PGCursorWrapper(con)
            con.commit()
        finally:
            con.close()
    else:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()


@contextmanager
def _auth_conn():
    """계정(로그인) 테이블 전용 — 사용자별 스키마/파일이 아니라 항상 고정된 한 곳을 쓴다
    (로그인 전엔 어느 사용자인지 아직 모르므로)."""
    if _use_pg():
        con = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            with con.cursor() as cur:
                cur.execute("SET search_path TO public")
            yield _PGCursorWrapper(con)
            con.commit()
        finally:
            con.close()
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        con = sqlite3.connect(AUTH_DB_PATH)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()


_SCHEMA_TICKERS_SCORECARDS = """
CREATE TABLE IF NOT EXISTS tickers (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,
    kind        TEXT DEFAULT 'long',
    notes       TEXT DEFAULT '',
    added_at    TEXT
);
CREATE TABLE IF NOT EXISTS scorecards (
    symbol      TEXT PRIMARY KEY,
    data        TEXT,
    updated_at  TEXT
);
"""

_SCHEMA_REST = """
CREATE TABLE IF NOT EXISTS assumptions (
    symbol      TEXT PRIMARY KEY,
    data        TEXT
);
CREATE TABLE IF NOT EXISTS scenarios (
    symbol      TEXT PRIMARY KEY,
    data        TEXT,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS peers (
    symbol      TEXT PRIMARY KEY,
    data        TEXT
);
"""

_SCHEMA_SQLITE = _SCHEMA_TICKERS_SCORECARDS + """
CREATE TABLE IF NOT EXISTS catalysts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT,
    date        TEXT,
    kind        TEXT,
    headline    TEXT,
    price_at    REAL,
    expected_impact REAL,
    reflected_pct   REAL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT,
    date        TEXT,
    action      TEXT,
    price       REAL,
    shares      REAL,
    reason      TEXT
);
""" + _SCHEMA_REST

_SCHEMA_PG = _SCHEMA_TICKERS_SCORECARDS + """
CREATE TABLE IF NOT EXISTS catalysts (
    id          SERIAL PRIMARY KEY,
    symbol      TEXT,
    date        TEXT,
    kind        TEXT,
    headline    TEXT,
    price_at    REAL,
    expected_impact REAL,
    reflected_pct   REAL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id          SERIAL PRIMARY KEY,
    symbol      TEXT,
    date        TEXT,
    action      TEXT,
    price       REAL,
    shares      REAL,
    reason      TEXT
);
""" + _SCHEMA_REST


def init_db(db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.executescript(_SCHEMA_PG if _use_pg() else _SCHEMA_SQLITE)


# ---- 계정(로그인) ----
def init_auth_db() -> None:
    with _auth_conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                name        TEXT PRIMARY KEY,
                pw_hash     TEXT NOT NULL,
                pw_salt     TEXT NOT NULL,
                created_at  TEXT
            )
            """
        )


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return dk.hex(), salt.hex()


def user_exists(name: str) -> bool:
    init_auth_db()
    with _auth_conn() as con:
        row = con.execute("SELECT 1 FROM users WHERE name=?", (name.strip(),)).fetchone()
        return row is not None


def create_user(name: str, password: str) -> bool:
    """신규 계정 생성. 이름이 이미 있으면 False(생성 안 함)."""
    name = name.strip()
    init_auth_db()
    with _auth_conn() as con:
        if con.execute("SELECT 1 FROM users WHERE name=?", (name,)).fetchone():
            return False
        pw_hash, salt = _hash_password(password)
        con.execute(
            "INSERT INTO users(name, pw_hash, pw_salt, created_at) VALUES (?,?,?,?)",
            (name, pw_hash, salt, _now()),
        )
        return True


def verify_password(name: str, password: str) -> bool:
    init_auth_db()
    with _auth_conn() as con:
        row = con.execute("SELECT pw_hash, pw_salt FROM users WHERE name=?",
                          (name.strip(),)).fetchone()
        if not row:
            return False
        row = dict(row)
        computed, _ = _hash_password(password, bytes.fromhex(row["pw_salt"]))
        return hmac.compare_digest(computed, row["pw_hash"])


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---- tickers ----
def add_ticker(symbol: str, name: str, kind: str = "long", db_path: str = DB_PATH) -> None:
    symbol = symbol.upper().strip()
    with _conn(db_path) as con:
        con.execute(
            "INSERT OR IGNORE INTO tickers(symbol, name, kind, added_at) VALUES (?,?,?,?)",
            (symbol, name, kind, _now()),
        )


def update_ticker(symbol: str, name: str | None = None, kind: str | None = None,
                  notes: str | None = None, db_path: str = DB_PATH) -> None:
    sets, vals = [], []
    for col, v in (("name", name), ("kind", kind), ("notes", notes)):
        if v is not None:
            sets.append(f"{col}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(symbol.upper().strip())
    with _conn(db_path) as con:
        con.execute(f"UPDATE tickers SET {', '.join(sets)} WHERE symbol=?", vals)


def remove_ticker(symbol: str, db_path: str = DB_PATH) -> None:
    symbol = symbol.upper().strip()
    with _conn(db_path) as con:
        for tbl in ("tickers", "scorecards", "assumptions", "scenarios", "peers"):
            con.execute(f"DELETE FROM {tbl} WHERE symbol=?", (symbol,))
        for tbl in ("catalysts", "trades"):
            con.execute(f"DELETE FROM {tbl} WHERE symbol=?", (symbol,))


def list_tickers(db_path: str = DB_PATH) -> list[dict]:
    with _conn(db_path) as con:
        rows = con.execute("SELECT * FROM tickers ORDER BY added_at DESC").fetchall()
        return [dict(r) for r in rows]


# ---- scorecards ----
def save_scorecard(symbol: str, items: list[dict], db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute(
            "INSERT INTO scorecards(symbol, data, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (symbol.upper().strip(), json.dumps(items, ensure_ascii=False), _now()),
        )


def load_scorecard(symbol: str, db_path: str = DB_PATH) -> list[dict] | None:
    with _conn(db_path) as con:
        row = con.execute("SELECT data FROM scorecards WHERE symbol=?",
                          (symbol.upper().strip(),)).fetchone()
        return json.loads(row["data"]) if row else None


# ---- catalysts ----
def add_catalyst(symbol: str, date: str, kind: str, headline: str, price_at: float,
                 expected_impact: float, reflected_pct: float, note: str = "",
                 db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute(
            "INSERT INTO catalysts(symbol,date,kind,headline,price_at,expected_impact,"
            "reflected_pct,note) VALUES (?,?,?,?,?,?,?,?)",
            (symbol.upper().strip(), date, kind, headline, price_at, expected_impact,
             reflected_pct, note),
        )


def list_catalysts(symbol: str, db_path: str = DB_PATH) -> list[dict]:
    with _conn(db_path) as con:
        rows = con.execute("SELECT * FROM catalysts WHERE symbol=? ORDER BY date DESC",
                           (symbol.upper().strip(),)).fetchall()
        return [dict(r) for r in rows]


def delete_catalyst(cid: int, db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute("DELETE FROM catalysts WHERE id=?", (cid,))


# ---- trades ----
def add_trade(symbol: str, date: str, action: str, price: float, shares: float,
              reason: str = "", db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute(
            "INSERT INTO trades(symbol,date,action,price,shares,reason) VALUES (?,?,?,?,?,?)",
            (symbol.upper().strip(), date, action, price, shares, reason),
        )


def list_trades(symbol: str | None = None, db_path: str = DB_PATH) -> list[dict]:
    with _conn(db_path) as con:
        if symbol:
            rows = con.execute("SELECT * FROM trades WHERE symbol=? ORDER BY date",
                               (symbol.upper().strip(),)).fetchall()
        else:
            rows = con.execute("SELECT * FROM trades ORDER BY date").fetchall()
        return [dict(r) for r in rows]


def delete_trade(tid: int, db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute("DELETE FROM trades WHERE id=?", (tid,))


def position_summary(symbol: str, db_path: str = DB_PATH) -> dict:
    """매매기록으로 보유수량/평균단가 계산 (BUY 가산, SELL 차감)."""
    shares = 0.0
    cost = 0.0
    for t in list_trades(symbol, db_path):
        if t["action"] == "BUY":
            shares += t["shares"]
            cost += t["shares"] * t["price"]
        elif t["action"] == "SELL":
            if shares > 0:
                avg = cost / shares
                cost -= min(t["shares"], shares) * avg
            shares -= t["shares"]
    avg_price = cost / shares if shares > 0 else 0.0
    return {"shares": shares, "avg_price": avg_price, "cost_basis": cost}


# ---- assumptions ----
def save_assumptions(symbol: str, data: dict, db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute(
            "INSERT INTO assumptions(symbol,data) VALUES (?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET data=excluded.data",
            (symbol.upper().strip(), json.dumps(data, ensure_ascii=False)),
        )


def load_assumptions(symbol: str, db_path: str = DB_PATH) -> dict | None:
    with _conn(db_path) as con:
        row = con.execute("SELECT data FROM assumptions WHERE symbol=?",
                          (symbol.upper().strip(),)).fetchone()
        return json.loads(row["data"]) if row else None


# ---- scenarios (Bear/Base/Bull/Super Bull 케이스) ----
def save_scenario(symbol: str, data: dict, db_path: str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute(
            "INSERT INTO scenarios(symbol,data,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (symbol.upper().strip(), json.dumps(data, ensure_ascii=False), _now()),
        )


def load_scenario(symbol: str, db_path: str = DB_PATH) -> dict | None:
    with _conn(db_path) as con:
        row = con.execute("SELECT data FROM scenarios WHERE symbol=?",
                          (symbol.upper().strip(),)).fetchone()
        return json.loads(row["data"]) if row else None


# ---- peers (동종업계 비교 티커) ----
def save_peers(symbol: str, peers: list[str], db_path: str = DB_PATH) -> None:
    clean = [p.upper().strip() for p in peers if p and p.strip()]
    with _conn(db_path) as con:
        con.execute(
            "INSERT INTO peers(symbol,data) VALUES (?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET data=excluded.data",
            (symbol.upper().strip(), json.dumps(clean, ensure_ascii=False)),
        )


def load_peers(symbol: str, db_path: str = DB_PATH) -> list[str]:
    with _conn(db_path) as con:
        row = con.execute("SELECT data FROM peers WHERE symbol=?",
                          (symbol.upper().strip(),)).fetchone()
        return json.loads(row["data"]) if row else []
