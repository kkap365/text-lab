# 文字实验室（Zero to Tech）

一个中文文本分析服务：输入一段文本，返回情感得分、拼音与标签，并记录历史与分析排行。

前端 Next.js 构建为静态产物，由 Nginx 托管并反向代理 `/api`；后端 FastAPI 提供服务，
数据落 MySQL，热点结果缓存到 Redis。已部署在阿里云轻量服务器（2C2G）。

---

## 功能

| 功能 | 说明 |
|---|---|
| 情感分析 | SnowNLP 计算 0~1 情感得分，映射为「偏积极 / 中性 / 偏消极」 |
| 拼音转换 | pypinyin 生成带声调拼音 |
| 历史记录 | 按用户隔离，主键倒序分页 |
| 热门排行 | Redis ZSET 维护，`ZREVRANGE` 取 TOP N |
| 注册登录 | JWT + bcrypt，鉴权收敛为一个 `get_current_user` 依赖 |

---

## 技术栈

- **后端**：Python 3.12 / FastAPI / SQLAlchemy / PyMySQL
- **存储**：MySQL（业务数据）、Redis（结果缓存 + 排行榜）
- **NLP**：SnowNLP（情感分析）、pypinyin（拼音）
- **鉴权**：python-jose（JWT）、passlib[bcrypt]
- **前端**：Next.js（静态导出）
- **部署**：Nginx（静态托管 + 反向代理）、uvicorn

---

## 目录结构

```
.
├── backend/
│   ├── main.py            # 全部接口与业务逻辑
│   ├── requirements.txt
│   └── handmade.py        # 早期实验代码
├── app/                   # Next.js App Router
│   ├── layout.jsx         # 全站外壳
│   ├── page.jsx           # 首页
│   └── text-lab/page.jsx  # 文字实验室页
├── components/            # 前端组件
├── css/                   # 全站样式
└── package.json
```

---

## 本地运行

**1. 准备数据库**

```sql
CREATE DATABASE blog DEFAULT CHARSET utf8mb4;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE analyses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  text VARCHAR(2000) NOT NULL,
  pinyin TEXT,
  score FLOAT,
  label VARCHAR(20),
  user_id INT,
  created_at VARCHAR(50)
);
```

**2. 后端**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # 填入 DATABASE_URL 与 JWT_SECRET
python main.py              # 或 uvicorn main:app --host 127.0.0.1 --port 8000
```

需要本地有 MySQL 和 Redis 在跑（默认 `localhost:3306` / `localhost:6379`）。

**3. 前端**

```bash
npm install
npm run build      # 产出静态文件到 out/
```

---

## 环境变量

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | MySQL 连接串，如 `mysql+pymysql://user:pass@localhost/blog` |
| `JWT_SECRET` | JWT 签名密钥，生产环境请用随机长字符串 |

代码通过 `os.getenv` 读取，未配置时会用默认值（仅适用于本地开发）。

---

## 部署方式

服务器上不跑 Node，只跑 Nginx + uvicorn：

```
浏览器
  └─ Nginx :80
       ├─ /          → 静态文件（Next.js 构建产物 out/）
       └─ /api/*     → 反代到 127.0.0.1:8000（uvicorn）
```

- **前端构建在本地做**，`out/` 用 `scp` 上传，服务器无需安装 Node
- **`/api` 走同源反向代理**，所以前端不需要处理跨域，后端也无需配置 CORS 白名单
- 更新流程：本地构建 → 备份线上文件 → `scp` 上传 → 校验 → 重启 uvicorn → curl 回归

---

## 几个设计取舍

**SnowNLP 放在同步路由里。**
情感分析是纯 CPU 计算。如果写进 `async def`，会阻塞事件循环，一个请求算的时候其他请求全部排队。
所以路由用普通 `def`，由 FastAPI 自动交给线程池执行——计算期间事件循环仍能响应其他接口。

**前端不走 Node 运行时。**
2C2G 的机器上多一个常驻 Node 进程会明显吃内存。所以前端在本地构建成静态产物，
服务器只保留 Nginx，省掉一份常驻内存。

**鉴权收敛为一个依赖。**
用户校验写在 `get_current_user` 里，业务接口只声明依赖，不重复解析 token。

---

## 已知限制

- **缓存 key 直接用原文**，没有做哈希与版本前缀——长文本作为 key 占用较大，模型或策略变更后无法平滑失效
- **MySQL 与 Redis 没有共同事务**：落库成功但 `zincrby` 失败会少计一次，数据不脏但统计口径会偏
- **缓存击穿未做防护**：分析结果是纯函数、重建成本毫秒级、无外部依赖，评估后认为影响可控
- **uvicorn 单进程**：未做多 worker，并发上限受单个进程限制

---

## License

MIT
