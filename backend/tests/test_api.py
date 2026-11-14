"""接口鉴权与入参校验测试。

这五个用例都只走到「鉴权」或「入参校验」阶段就返回，
不会访问 MySQL 或 Redis，因此不需要真实数据库就能跑。

跑法（在 backend 目录下）：
    python -m pytest tests/ -v
"""
from fastapi.testclient import TestClient

from main import app, get_current_user

client = TestClient(app)


# ── 鉴权：不带 token 应被拦截 ──────────────────────────────

def test_history_requires_auth():
    """不带 token 请求历史记录，应返回 401。"""
    r = client.get("/api/history")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_analyze_requires_auth():
    """不带 token 请求分析接口，应返回 401。"""
    r = client.post("/api/analyze", json={"text": "测试"})
    assert r.status_code == 401


def test_analyze_rejects_invalid_token():
    """带非法 token，应返回 401 而不是 500。"""
    r = client.post(
        "/api/analyze",
        json={"text": "测试"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid token"


# ── 入参校验：需要绕过鉴权才能测到这里 ────────────────────

def _override_auth():
    """把 get_current_user 替换成固定返回 1 的假依赖。"""
    app.dependency_overrides[get_current_user] = lambda: 1


def _clear_override():
    app.dependency_overrides.clear()


def test_analyze_rejects_non_string_text():
    """text 传数字应被 Pydantic 拦成 422，而不是进到业务逻辑。"""
    _override_auth()
    try:
        r = client.post("/api/analyze", json={"text": 123})
        assert r.status_code == 422
        detail = r.json()["detail"][0]
        assert detail["type"] == "string_type"
        assert detail["loc"] == ["body", "text"]
    finally:
        _clear_override()


def test_analyze_rejects_empty_text():
    """纯空格文本应返回 400，而不是算出 0.5 的「中性」。"""
    _override_auth()
    try:
        r = client.post("/api/analyze", json={"text": "   "})
        assert r.status_code == 400
        assert "不能为空" in r.json()["detail"]
    finally:
        _clear_override()


def test_analyze_rejects_too_long_text():
    """超过 2000 字应返回 400，而不是让数据库层报错变成 500。"""
    _override_auth()
    try:
        r = client.post("/api/analyze", json={"text": "测" * 2001})
        assert r.status_code == 400
        assert "过长" in r.json()["detail"]
    finally:
        _clear_override()
