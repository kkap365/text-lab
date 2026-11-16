"""业务逻辑：纯计算和状态转换，不依赖 FastAPI。

拆出来的目的：
  · 这些函数可以直接单元测试，不需要发 HTTP 请求
  · 路由层只负责「校验 → 调用 → 返回」，变薄
  · 换 Web 框架时，这一层不用动
"""
from datetime import datetime, timezone

from pypinyin import Style, lazy_pinyin
from snownlp import SnowNLP


def score_label(score: float) -> str:
    """把 0~1 的情感得分映射成三档标签。"""
    if score >= 0.6:
        return "偏积极"
    if score <= 0.4:
        return "偏消极"
    return "中性"


def analyze_text(text: str) -> dict:
    """分析一段文本，返回得分、标签和拼音。

    纯函数：不读写数据库，不碰缓存，同样的输入永远同样的输出
    （除了 created_at）。
    """
    score = round(SnowNLP(text).sentiments, 2)
    return {
        "text": text,
        "score": score,
        "label": score_label(score),
        "pinyin": " ".join(lazy_pinyin(text, style=Style.TONE)),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def validate_text(text: str, max_len: int) -> str:
    """入参校验：返回 strip 后的文本，不合法时抛 ValueError。

    放在 service 层而不是路由层，是因为「多长算超长」属于业务规则，
    不属于 HTTP。路由层只负责把 ValueError 转成 400。
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("文本不能为空")
    if len(cleaned) > max_len:
        raise ValueError(f"文本过长，最多{max_len}字")
    return cleaned
