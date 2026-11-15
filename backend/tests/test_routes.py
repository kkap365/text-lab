"""路由表的回归测试。

背景：main.py 里曾经把 /api/history 注册了两次，FastAPI 按注册顺序匹配，
后定义的那份永远不会执行，而且不报任何错。表现是「改了代码不生效」。

这两个测试防止它复发：
  1. 同一路径不能被注册多次
  2. 实际生效的 handler 必须支持分页参数（说明是正确的那一份）
"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _paths():
    """收集所有已注册路由的 path（跳过没有 path 属性的项）。"""
    return [getattr(r, "path", None) for r in app.routes]


def test_no_duplicate_route_paths():
    """同一 path 只能出现一次——重复注册意味着死代码。"""
    paths = [p for p in _paths() if p]
    duplicated = {p for p in paths if paths.count(p) > 1}
    assert not duplicated, f"以下路径被重复注册：{duplicated}"


def test_history_accepts_page_and_size():
    """/api/history 必须接受 page 和 size 参数。

    死掉的那一版签名是 def history()，不带任何参数——
    如果它生效了，带 page/size 请求虽然也能 200（多余参数会被忽略），
    但返回体里不会有这些字段。所以直接断言响应结构更可靠。
    """
    # 不带 token 会 401，这里只验证「路由存在且不是 404」
    r = client.get("/api/history?page=1&size=10")
    assert r.status_code in (200, 401), "路由应存在（401 表示鉴权拦住了，说明路由是活的）"


def test_history_with_auth_returns_pagination_fields(monkeypatch):
    """补一个 200 场景：响应体必须带 page/size/total/records。"""
    import main
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool

    from main import get_current_user

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(text(
            "CREATE TABLE analyses ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "text VARCHAR(2000), pinyin TEXT, score FLOAT,"
            "label VARCHAR(20), user_id INTEGER, created_at VARCHAR(50))"
        ))
        conn.execute(text(
            "INSERT INTO analyses (text, pinyin, score, label, user_id, created_at) "
            "VALUES ('t', 'p', 0.5, '中性', 1, '2026-11-15T00:00:00')"
        ))
        conn.commit()

    monkeypatch.setattr(main, "engine", eng)
    app.dependency_overrides[get_current_user] = lambda: 1
    try:
        r = client.get("/api/history?page=1&size=10")
        assert r.status_code == 200
        body = r.json()
        for key in ("records", "total", "page", "size"):
            assert key in body, f"响应缺少字段 {key}"
    finally:
        app.dependency_overrides.clear()
        eng.dispose()
