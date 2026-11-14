"""历史记录接口的隔离与越权测试。

这两个能力是昨天改的：
  · /api/history 按 user_id 过滤
  · /api/history/{id} 校验记录归属，404 与 403 分开

测试用 SQLite 内存库替换 MySQL，靠 monkeypatch 改掉 main.engine，
所以不需要任何外部服务。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import main
from main import app, get_current_user

client = TestClient(app)

USER_A = 1
USER_B = 2

SCHEMA = """
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text VARCHAR(2000) NOT NULL,
    pinyin TEXT,
    score FLOAT,
    label VARCHAR(20),
    user_id INTEGER,
    created_at VARCHAR(50)
)
"""


@pytest.fixture
def db(monkeypatch):
    """把 main.engine 换成 SQLite 内存库，并准备两个用户的数据。

    用 StaticPool 让内存库在多个连接间共享——默认每次 connect 都会
    新建一个空库，测试就查不到刚插入的数据。
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(text(SCHEMA))
        rows = [
            ("A 的第一条", "a1", 0.9, "偏积极", USER_A, "2026-11-14T01:00:00+00:00"),
            ("A 的第二条", "a2", 0.2, "偏消极", USER_A, "2026-11-14T01:01:00+00:00"),
            ("B 的一条", "b1", 0.5, "中性", USER_B, "2026-11-14T01:02:00+00:00"),
        ]
        for r in rows:
            conn.execute(
                text(
                    "INSERT INTO analyses (text, pinyin, score, label, user_id, created_at) "
                    "VALUES (:t, :p, :s, :l, :u, :c)"
                ),
                {"t": r[0], "p": r[1], "s": r[2], "l": r[3], "u": r[4], "c": r[5]},
            )
        conn.commit()

    monkeypatch.setattr(main, "engine", eng)
    yield eng
    eng.dispose()


def as_user(uid):
    app.dependency_overrides[get_current_user] = lambda: uid


@pytest.fixture(autouse=True)
def clean_overrides():
    yield
    app.dependency_overrides.clear()


# ── 历史记录：只能看到自己的 ──────────────────────────────

def test_history_only_returns_own_records(db):
    """A 登录后只能看到 A 的两条，看不到 B 的。"""
    as_user(USER_A)
    r = client.get("/api/history")
    assert r.status_code == 200

    body = r.json()
    texts = [x["text"] for x in body["records"]]
    assert "A 的第一条" in texts
    assert "A 的第二条" in texts
    assert "B 的一条" not in texts
    assert body["total"] == 2, "total 也必须是当前用户的条数"


def test_history_pagination_respects_ownership(db):
    """分页的 total 只算自己的，不会把别人的算进去。"""
    as_user(USER_B)
    r = client.get("/api/history?page=1&size=10")
    assert r.status_code == 200

    body = r.json()
    assert body["total"] == 1
    assert [x["text"] for x in body["records"]] == ["B 的一条"]


# ── 删除：404 与 403 必须分开 ─────────────────────────────

def test_delete_missing_record_returns_404(db):
    """删不存在的 id 应该 404。"""
    as_user(USER_A)
    r = client.delete("/api/history/99999")
    assert r.status_code == 404
    assert r.json()["detail"] == "记录不存在"


def test_delete_other_users_record_returns_403(db):
    """A 删 B 的记录应该 403，而不是静默成功。"""
    with db.connect() as conn:
        b_id = conn.execute(
            text("SELECT id FROM analyses WHERE user_id = :u"), {"u": USER_B}
        ).fetchone()[0]

    as_user(USER_A)
    r = client.delete(f"/api/history/{b_id}")
    assert r.status_code == 403
    assert r.json()["detail"] == "无权删除该记录"

    # 关键：B 的记录必须还在
    with db.connect() as conn:
        still = conn.execute(
            text("SELECT COUNT(*) FROM analyses WHERE id = :i"), {"i": b_id}
        ).fetchone()[0]
    assert still == 1, "403 之后记录不能被删掉"


def test_delete_own_record_succeeds(db):
    """A 删自己的记录应该成功，且只删掉那一条。"""
    with db.connect() as conn:
        a_id = conn.execute(
            text("SELECT id FROM analyses WHERE user_id = :u ORDER BY id LIMIT 1"),
            {"u": USER_A},
        ).fetchone()[0]

    as_user(USER_A)
    r = client.delete(f"/api/history/{a_id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    with db.connect() as conn:
        left = conn.execute(
            text("SELECT COUNT(*) FROM analyses WHERE user_id = :u"), {"u": USER_A}
        ).fetchone()[0]
    assert left == 1, "自己的两条应该只剩一条"
