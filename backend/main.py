from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from pypinyin import lazy_pinyin, Style
from snownlp import SnowNLP
import json
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
import redis
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
def load_history():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT text, pinyin, score, label, created_at "
            "FROM analyses ORDER BY id DESC LIMIT 20"
        ))
        return [dict(row) for row in result]

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str
class AnalyzeRequest(BaseModel):
    text: str

app = FastAPI()


from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

engine = create_engine(os.getenv("DATABASE_URL", "mysql+pymysql://user:password@localhost/blog"))
def save_record(record,user_id):
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO analyses (text, pinyin, score, label, created_at, user_id) "
            "VALUES (:text, :pinyin, :score, :label, :created_at, :user_id)"
        ), {**record, "user_id": user_id})
        conn.commit()

# 密码加密工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置（secret 要换成你自己的随机字符串）
SECRET_KEY = os.getenv("JWT_SECRET", "dev-only-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60*24  # token 24小时有效
bearer = HTTPBearer(auto_error=False)

def get_current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if cred is None:                       # 没带 Authorization 头
        raise HTTPException(status_code=401, detail="Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    try:                                   # 验签（用的必须是 login 里 encode 同一套常量）
        payload = jwt.decode(cred.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    uid = payload.get("sub")               # login 里 sub 装的就是 user.id
    try:
        return int(uid)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
# 注册
@app.post("/api/register")
def register(req: RegisterRequest):
    username = req.username
    password = req.password
    with engine.connect() as conn:
        # 查是否已存在
        exists = conn.execute(text(
            "SELECT id FROM users WHERE username=:u"
        ), {"u": username}).fetchone()
        if exists:
            return {"error": "用户名已存在"}
        # 密码加密后存入
        hashed = pwd_context.hash(password)
        conn.execute(text(
            "INSERT INTO users (username, password_hash) VALUES (:u, :h)"
        ), {"u": username, "h": hashed})
        conn.commit()
    return {"ok": True}

# 登录（验证密码，发 token）

@app.post("/api/login")
def login(req: LoginRequest):
    username = req.username
    password = req.password
    with engine.connect() as conn:
        user = conn.execute(text(
            "SELECT id, username, password_hash FROM users WHERE username=:u"
        ), {"u": username}).fetchone()
    if not user:
        return {"error": "用户不存在"}
    if not pwd_context.verify(password, user.password_hash):
        return {"error": "密码错误"}
    # 生成 token
    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)},
        SECRET_KEY, algorithm=ALGORITHM
    )
    return {"token": token, "username": user.username}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://47.116.131.129"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        records = []
        for row in result:
            records.append({
                "text": row[0],
                "pinyin": row[1],
                "score": row[2],
                "label": row[3],
                "created_at": row[4],
            })
    return {"records": records, "total": total, "page": page, "size": size}

@app.delete("/api/history/{record_id}")
def delete_history(record_id: int, user_id: int = Depends(get_current_user)):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT user_id FROM analyses WHERE id = :id"),
            {"id": record_id},
        ).fetchone()
        # 404 与 403 分开：先判存在，再判归属。
        # 若统一返回 403，会泄露「这条记录存在」这一信息。
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        if row[0] != user_id:
            raise HTTPException(status_code=403, detail="无权删除该记录")
        conn.execute(
            text("DELETE FROM analyses WHERE id = :id"),
            {"id": record_id},
        )
        conn.commit()
    return {"ok": True}

def score_label(score):
    if score >= 0.6:
        return "偏积极"
    elif score <= 0.4:
        return "偏消极"
    else:
        return "中性"

@app.get("/api/history")
def history():
    records = load_history()   # 读出文件里的全部记录
    return records

@app.get("/api/hot")
def hot():
    top = r.zrevrange("hot_texts", 0, 9, withscores=True)
    return {"hot": [{"text": t, "count": int(c)} for t, c in top]}
MAX_LEN = 2000

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, user_id: int = Depends(get_current_user)):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本不能为空")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="文本过长，最多2000字")
    print("收到分析请求:", text)
    # 先查缓存
    cached = r.get(f"analysis:{text}")
    if cached:
        print("命中缓存！")
        return json.loads(cached)
    # 缓存没有 → 正常分析
    score = round(SnowNLP(text).sentiments, 2)
    result = {
        "text": text,
        "score": score,
        "label": score_label(score),
        "pinyin": " ".join(lazy_pinyin(text, style=Style.TONE)),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_record(result,user_id)
    r.setex(f"analysis:{text}", 600, json.dumps(result, ensure_ascii=False))
    r.zincrby("hot_texts", 1, text)
    return result
    