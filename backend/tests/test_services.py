"""业务逻辑的单元测试。

这组测试的意义：services.py 里的函数是纯逻辑，不依赖 FastAPI、
不依赖数据库、不依赖 Redis —— 所以可以直接调用、毫秒级跑完。

对比：test_api.py 里的测试要发 HTTP 请求、走依赖注入、走 Pydantic 校验。
分层的价值就在这里 —— 越底层的逻辑越好测。
"""
import pytest

from services import analyze_text, score_label, validate_text


# ── score_label：三档映射的边界 ───────────────────────

@pytest.mark.parametrize(
    "score, expected",
    [
        (1.0, "偏积极"),
        (0.6, "偏积极"),   # 边界：>= 0.6 就是积极
        (0.59, "中性"),
        (0.5, "中性"),
        (0.41, "中性"),
        (0.4, "偏消极"),   # 边界：<= 0.4 就是消极
        (0.0, "偏消极"),
    ],
)
def test_score_label_boundaries(score, expected):
    """三档的边界值必须精确 —— 0.6 算积极、0.4 算消极。"""
    assert score_label(score) == expected


# ── analyze_text：输出结构 ────────────────────────────

def test_analyze_text_returns_expected_fields():
    """返回体必须有这五个字段，前端按这个结构渲染。"""
    result = analyze_text("今天的风很轻，适合把脑海里的想法慢慢写下来。")

    assert set(result) == {"text", "score", "label", "pinyin", "created_at"}
    assert result["text"].startswith("今天的风很轻")
    assert 0.0 <= result["score"] <= 1.0
    assert result["label"] in ("偏积极", "中性", "偏消极")
    assert result["pinyin"]      # 拼音非空
    assert "T" in result["created_at"]  # ISO 格式带 T


def test_analyze_text_is_deterministic_except_timestamp():
    """同样的输入，除时间戳外结果必须完全一致 —— 这也是它能被缓存的前提。"""
    text = "苹果是一种水果。"
    a = analyze_text(text)
    b = analyze_text(text)

    assert a["score"] == b["score"]
    assert a["label"] == b["label"]
    assert a["pinyin"] == b["pinyin"]


# ── validate_text：入参边界 ───────────────────────────

def test_validate_text_strips_whitespace():
    """前后空格应该被去掉，返回干净的文本。"""
    assert validate_text("  你好  ", 2000) == "你好"


def test_validate_text_rejects_empty():
    """纯空格等于空，必须报错而不是算出 0.5 的中性分。"""
    with pytest.raises(ValueError, match="不能为空"):
        validate_text("    ", 2000)


def test_validate_text_rejects_too_long():
    """超过上限要报错，消息里带上限制值。"""
    with pytest.raises(ValueError, match="文本过长，最多2000字"):
        validate_text("测" * 2001, 2000)


def test_validate_text_accepts_exact_limit():
    """正好等于上限，应该通过（边界不能多拦一个）。"""
    text = "测" * 2000
    assert validate_text(text, 2000) == text
