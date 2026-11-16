"""重构后的 main.py（第一步：拆分业务逻辑与配置）。

改动：
  · Pydantic 模型 → schemas.py
  · 配置常量     → config.py
  · 纯业务逻辑   → services.py
  · 本文件只剩：app 创建、中间件、鉴权依赖、路由定义

行数对比：218 行 → 约 120 行
"""
import json
from datetime import datetime, timedelta, timezone

import redis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import create_engine, text

import config
import services
from schemas import AnalyzeRequest, LoginRequest, RegisterRequest

app = FastAPI()

# ── 存储 ──────────────────────────────────────────────

r = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT,
                db=config.REDIS_DB, decode_responses=True)

engine = create_engine(config.DATABASE_URL)


def save_record(record: dict, user_id: int) -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO analyses (text, pinyin, score, label, created_at, user_id) "
                "VALUES (:text, :pinyin, :score, :label, :created_at, :user_id)"
            ),
            {**record, "user_id": user_id},
        )
        conn.commit()


# ── 鉴权 ──────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def get_current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    if cred is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            cred.credentials, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


# ── 中间件 ────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://47.116.131.129"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由：账户 ────────────────────────────────────────

@app.post("/api/register")
def register(req: RegisterRequest):
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT id FROM users WHERE username=:u"), {"u": req.username}
        ).fetchone()
        if exists:
            return {"error": "用户名已存在"}
        conn.execute(
            text("INSERT INTO users (username, password_hash) VALUES (:u, :h)"),
            {"u": req.username, "h": pwd_context.hash(req.password)},
        )
        conn.commit()
    return {"ok": True}


@app.post("/api/login")
def login(req: LoginRequest):
    with engine.connect() as conn:
        user = conn.execute(
            text("SELECT id, username, password_hash FROM users WHERE username=:u"),
            {"u": req.username},
        ).fetchone()
    if not user:
        return {"error": "用户不存在"}
    if not pwd_context.verify(req.password, user.password_hash):
        return {"error": "密码错误"}
    token = jwt.encode(
        {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=config.TOKEN_EXPIRE_MINUTES),
        },
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM,
    )
    return {"token": token, "username": user.username}


# ── 路由：首页配置 ────────────────────────────────────

profile = {
    "heroTitle": "关于我",
    "heroSubtitle": "项目，创意，灵感，心得，我的作品",
    "featuredWork": {
        "kicker": "作品",
        "title": "文字实验室",
        "copy": "拼音和情绪，挖掘中文里的细节",
        "linkLabel": "打开作品",
    },
    "identity": {
        "motto": "已识乾坤大，尤怜草木青",
        "learning": "零到全栈",
    },
}


@app.get("/api/profile")
def get_profile():
    return profile


# ── 路由：分析 ────────────────────────────────────────

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, user_id: int = Depends(get_current_user)):
    try:
        text = services.validate_text(req.text, config.TEXT_MAX_LEN)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cached = r.get(f"analysis:{text}")
    if cached:
        return json.loads(cached)

    result = services.analyze_text(text)
    save_record(result, user_id)
    r.setex(f"analysis:{text}", config.ANALYSIS_CACHE_TTL,
            json.dumps(result, ensure_ascii=False))
    r.zincrby(config.HOT_TEXTS_KEY, 1, text)
    return result


@app.get("/api/hot")
def hot():
    top = r.zrevrange(config.HOT_TEXTS_KEY, 0, config.HOT_TOP_N - 1, withscores=True)
    return {"hot": [{"text": t, "count": int(c)} for t, c in top]}


# ── 路由：历史记录 ────────────────────────────────────

@app.get("/api/history")
def history(page: int = 1, size: int = 10, user_id: int = Depends(get_current_user)):
    offset = (page - 1) * size
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM analyses WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()[0]
        result = conn.execute(
            text(
                "SELECT text, pinyin, score, label, created_at FROM analyses "
                "WHERE user_id = :uid ORDER BY id DESC LIMIT :lim OFFSET :off"
            ),
            {"uid": user_id, "lim": size, "off": offset},
        )
        records = [
            {
                "text": row[0],
                "pinyin": row[1],
                "score": row[2],
                "label": row[3],
                "created_at": row[4],
            }
            for row in result
        ]
    return {"records": records, "total": total, "page": page, "size": size}


@app.delete("/api/history/{record_id}")
def delete_history(record_id: int, user_id: int = Depends(get_current_user)):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT user_id FROM analyses WHERE id = :id"), {"id": record_id}
        ).fetchone()
        # 404 与 403 分开：先判存在，再判归属。
        # 若统一返回 403，会泄露「这条记录存在」这一信息。
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        if row[0] != user_id:
            raise HTTPException(status_code=403, detail="无权删除该记录")
        conn.execute(text("DELETE FROM analyses WHERE id = :id"), {"id": record_id})
        conn.commit()
    return {"ok": True}
