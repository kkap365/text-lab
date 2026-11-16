"""配置：全部从环境变量读取，未配置时用开发默认值。

集中放在这里的原因：原来 SECRET_KEY、DATABASE_URL、TTL、上限值
散落在 main.py 各处，改一个值要翻文件。
"""
import os

# ── 鉴权 ──────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时

# ── 存储 ──────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL", "mysql+pymysql://user:password@localhost/blog"
)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# ── 业务常量 ──────────────────────────────────────────
TEXT_MAX_LEN = 2000          # 单次分析的文本长度上限
ANALYSIS_CACHE_TTL = 600     # 分析结果缓存秒数
HOT_TEXTS_KEY = "hot_texts"  # 热门排行的 ZSET key
HOT_TOP_N = 10               # 排行榜取前 N
