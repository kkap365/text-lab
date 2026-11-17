# 文字实验室（Zero to Tech）

一个中文文本分析服务：输入一段文本，返回情感得分、拼音与标签，并记录历史与分析排行。

前端 Next.js 构建为静态产物由 Nginx 托管，后端 FastAPI 提供服务，数据落 MySQL，
热点结果缓存到 Redis。已部署在阿里云轻量服务器（2C2G）。

线上地址：http://47.116.131.129

---

## 一、技术栈

| 层 | 选型 |
|---|---|
| 后端框架 | Python 3.12 + FastAPI |
| 数据库 | MySQL 8（SQLAlchemy Core + PyMySQL） |
| 缓存 / 排行榜 | Redis（String 缓存 + ZSET 排行） |
| NLP | SnowNLP（情感分析）、pypinyin（拼音转换） |
| 鉴权 | JWT（python-jose）+ bcrypt（passlib） |
| 前端 | Next.js（App Router，静态导出） |
| 部署 | Nginx（静态托管 + 反向代理）+ uvicorn |

---

## 二、项目结构

```
.
├── backend/
│   ├── main.py              # 全部接口与业务逻辑
│   ├── requirements.txt
│   ├── .env.example         # 环境变量模板
│   └── handmade.py          # 早期实验代码
├── app/                     # Next.js App Router
│   ├── layout.jsx           # 全站外壳，统一引入 CSS
│   ├── page.jsx             # 首页
│   └── text-lab/page.jsx    # 文字实验室页
├── components/              # 前端组件
│   ├── Nav.jsx / PageHeading.jsx
│   ├── HomeView.jsx / TextLabView.jsx
│   ├── InputCard.jsx / ResultCard.jsx
│   └── LoginCard.jsx / AnimatedCardGrid.jsx
├── css/                     # 全站样式
├── package.json
└── README.md
```

---

## 三、接口列表

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | `/api/register` | 注册，密码经 bcrypt 哈希后入库 | 否 |
| POST | `/api/login` | 登录，校验密码后签发 JWT | 否 |
| GET | `/api/profile` | 返回首页个人介绍配置 | 否 |
| GET | `/api/history?page=&size=` | 分页查询历史记录 | 否 |
| DELETE | `/api/history/{record_id}` | 删除一条历史记录 | 否 |
| GET | `/api/hot` | 返回热门排行 TOP 10（Redis ZSET） | 否 |
| POST | `/api/analyze` | 情感分析主接口 | **是** |

`/api/analyze` 的鉴权通过 `Depends(get_current_user)` 注入：
从 `Authorization: Bearer <token>` 解析出 `user_id`，作为参数传入业务函数。

---

## 四、快速开始

### 1. 准备数据库

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

### 2. 启动后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # 填入 DATABASE_URL 与 JWT_SECRET
python main.py                   # 或 uvicorn main:app --host 127.0.0.1 --port 8000
```

依赖的 MySQL（3306）和 Redis（6379）需在本机运行。

### 3. 构建前端

```bash
npm install
npm run build        # 静态文件产出到 out/
```

---

## 五、环境变量

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | MySQL 连接串，如 `mysql+pymysql://user:pass@localhost/blog` |
| `JWT_SECRET` | JWT 签名密钥，生产环境应为随机长字符串 |

代码通过 `os.getenv` 读取，未配置时使用开发用默认值。
**仓库中不含任何真实密钥**，`.env` 已在 `.gitignore` 中排除。

---

## 六、部署方式

服务器上不运行 Node，只有 Nginx + uvicorn：

```
浏览器
  └─ Nginx :80
       ├─ /              → 静态文件（Next.js 构建产物 out/）
       └─ /api/*         → 反向代理到 127.0.0.1:8000（uvicorn）
```

具体做法：

1. **前端在本地构建**，`out/` 目录用 `scp` 上传到服务器，服务器不安装 Node
2. **`/api` 走同源反向代理**，所以前端不需要处理跨域，后端的 CORS 白名单只用于本地开发
3. **更新流程**：本地构建 → 备份线上目录 → `scp` 上传 → 校验文件 → 重启 uvicorn → curl 回归验证

---

## 七、几个设计说明

### 1. 为什么情感分析路由用 `def` 而不是 `async def`

SnowNLP 是纯 CPU 计算，不涉及网络 IO。如果写成 `async def`，计算期间会**阻塞事件循环**，
同一进程内所有其他请求都要排队等待。

写成普通 `def` 后，FastAPI 会把它**交给线程池执行**，事件循环在计算期间仍能响应其他请求。

> 注意：这不会加快计算本身（GIL 仍在），作用是不阻塞其他请求。

### 2. 为什么缓存 key 直接用文本

`analysis:{text}` —— 用原文当 key，实现简单、可读性好。

代价是长文本会占用较多 key 空间，且模型或算法变更后无法平滑失效。
如果继续优化，应该改成 `analysis:{sha256(text)}:{model_version}`。

### 3. 为什么用 ZSET 做排行

`ZINCRBY hot_texts 1 <text>` 累加计数，`ZREVRANGE hot_texts 0 9` 取 TOP 10。

相比 `SELECT text, COUNT(*) FROM analyses GROUP BY text ORDER BY COUNT(*) DESC`，
ZSET 的插入和范围查询都是 O(log N)，不需要全表扫描 + 排序。

### 4. 鉴权为什么收敛成一个依赖

用户校验写在 `get_current_user` 里，业务接口只声明依赖：

```python
@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, user_id: int = Depends(get_current_user)):
```

新增接口只要挂上这个依赖就自动完成鉴权，不需要在每个函数里重复解析 token。

---

## 八、本项目验证过的功能特性

按「一个特性 → 代码位置 → 怎么验证」列出来，便于按点查看：

| # | 功能特性 | 代码位置 | 验证方式 |
|---|---|---|---|
| 1 | **JWT 鉴权 + 依赖注入** | `get_current_user()` | 三态测试：无 token → 401、非法 token → 401、正常 token → 200 |
| 2 | **Pydantic 请求校验** | `AnalyzeRequest` 模型 | 发 `{"text": 123}` → 422 `string_type`，且业务函数未执行（日志无输出） |
| 3 | **入参边界处理** | `analyze()` 开头 | 空文本 → 400；超长文本 → 400（而非数据库层 500） |
| 4 | **Redis 缓存与 TTL** | `analyze()` 中 `r.get` / `r.setex` | 同文本二次请求耗时下降 + 日志出现「命中缓存」+ `ttl` 命令查剩余时间 |
| 5 | **ZSET 排行榜** | `hot()` 中 `zrevrange` | `zincrby` 累加后 `zrevrange` 取 TOP 10，不依赖数据库 `GROUP BY` |
| 6 | **分页查询走索引** | `history()` 中 `ORDER BY id DESC LIMIT` | `EXPLAIN` 结果 `type=index / key=PRIMARY / 无 filesort` |
| 7 | **静态托管与反向代理** | Nginx 配置 | 首页与 `/api/*` 均返回 200，`/api` 经反代到 uvicorn |

每一项的完整验证过程见 `测试记录.md`。

---

## 九、我的工作范围（如实说明）

| 部分 | 情况 |
|---|---|
| 项目结构与接口实现 | 参考了公开教程的思路，代码主体沿用教程 |
| 部署上线 | **本人完成**：Nginx 配置、静态产物上传、uvicorn 启动与守护 |
| 线上问题排查 | **本人完成**：见「已知问题」第 1 条与 `测试记录.md` |
| 数据库表设计与 EXPLAIN 验证 | **本人完成** |
| 环境变量改造 | **本人完成**：把硬编码的数据库密码与 JWT 密钥改为 `os.getenv` 读取 |

代码我可以逐行解释设计原因，但并非全部从零设计。

---

## 十、已知问题

### 1. `/api/history` 被注册了两次，后一个是死代码

`main.py` 第 137 行定义了一个带 `page`/`size` 参数的版本，第 175 行又定义了一个不带参数的版本。

**FastAPI 按注册顺序匹配，先注册的生效，后定义的永远不会执行，而且不报错。**

这个问题的发现过程：修改代码后重启服务，行为没有变化。依次排查了缓存、热重载、
部署是否生效，最后打印路由表才发现同一路径注册了两份。

**目前状态**：尚未删除第二个定义（需确认线上实际生效的是哪个版本）。
正确的修复是删掉无参数版本，并补一条路由回归测试防止复发。

### 2. 删除接口未校验记录归属

`DELETE /api/history/{record_id}` 只按 `id` 删除，没有校验该记录是否属于当前用户。
在生产环境中这是越权风险，应改为先查询 `user_id` 再比对。

### 3. 缓存击穿未做防护

热点文本的缓存过期瞬间，并发请求会同时穿透到计算层。

评估后暂未处理：情感分析是纯函数、单次计算毫秒级、无外部依赖，最坏情况是重复计算几次。
如果需要处理，方案是互斥锁（阻塞但实时）或逻辑过期（不阻塞但有短暂陈旧数据）。

### 4. MySQL 与 Redis 操作没有共同事务

`save_record()` 成功后，如果 `r.zincrby()` 失败，统计数据会少计一次。
数据不会脏，只是排行榜口径会偏。当前未处理。

---

## 十一、AI 工具使用说明

| 场景 | 是否使用 AI |
|---|---|
| 业务代码编写 | **否**，代码参考公开教程 |
| 理解报错信息、查询框架 API 用法 | 是 |
| 排查环境与依赖问题 | 是 |
| 本 README 初稿整理 | 是，内容经本人核对 |

所有代码本人可逐行解释。

---

## 许可

MIT

---

## 环境变量与部署

### 后端

| 变量 | 说明 | 缺失后果 |
|---|---|---|
| `DATABASE_URL` | MySQL 连接串 | **启动能成功，但第一次查库才 500** |
| `JWT_SECRET` | token 签名密钥 | 用开发默认值，重启后所有 token 失效 |
| `REDIS_HOST` / `REDIS_PORT` | Redis 地址，默认 `localhost:6379` | 缓存全部失效，降级为直接计算 |

**部署时通过启动脚本注入，不写死在代码里**（`/root/start_backend.sh`）：

```bash
#!/bin/bash
set -e

export DATABASE_URL="mysql+pymysql://<user>:<password>@localhost/<db>"

# 启动前校验：缺失或仍是占位符就立刻退出
if [ -z "$DATABASE_URL" ]; then
  echo "FATAL: DATABASE_URL 未设置" >&2
  exit 1
fi
if [[ "$DATABASE_URL" == *"user:password"* ]]; then
  echo "FATAL: DATABASE_URL 还是占位符" >&2
  exit 1
fi

cd /root/zero-to-tech/backend
exec /usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**为什么检查放在脚本而不是代码里**：应用代码不知道部署环境，而测试会 `import main`（那时没有环境变量）。放在启动脚本，校验只在真正部署时执行。

### 前端

| 变量 | 说明 |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | 后端地址。**留空则走同源相对路径 `/api`**，经 Nginx 反代到后端 |

**留空是推荐配置**：

```
NEXT_PUBLIC_API_BASE_URL=
```

请求变成 `/api/login`（相对路径）→ 同源 → Nginx 的 `location /api/` 转发到 `127.0.0.1:8000`。
这样后端端口不需要对公网开放。

> 注意：`NEXT_PUBLIC_*` 是**构建时内联**的，改完必须重新 `npm run build` 再传 `out/`，改服务器上的文件无效。

---

## 故障排查

记录几个上线过程中真实踩到的坑，都表现为「页面打不开」或「接口报错」，但原因完全不同。

### 1. 所有 `/api` 请求返回 HTML

**现象**：访问 `/api/profile` 返回的是前端页面，不是 JSON。
**原因**：Nginx 有两个 `server` 块 `listen 80` 且 `server_name` 相同，Nginx 只加载第一个，带 `location /api/` 的那个被忽略，请求落到 `try_files` 返回 `index.html`。
**定位**：`nginx -t` 会报 `conflicting server name "..." on 0.0.0.0:80, ignored`。
**修复**：合并成一个 server 块，删掉重复的配置文件。

### 2. 前端请求发到 `undefined/api/login`

**现象**：点登录提示"请求失败，请确认后端已启动"，Network 里 URL 是 `/undefined/api/login`。
**原因**：`process.env.NEXT_PUBLIC_API_BASE_URL` 是 `undefined`，拼进路径就成了 `undefined/api/...`。
**修复**：构建时设置 `.env.local`（留空走相对路径），或把代码写成 `process.env.NEXT_PUBLIC_API_BASE_URL || ""`。

### 3. 接口 500，日志是 `Access denied for user 'user'@'localhost'`

**现象**：`/api/profile` 正常（不查库），`/api/login` 500。
**原因**：`DATABASE_URL` 用了代码里的占位符默认值，服务能启动，但第一次连数据库才失败。
**修复**：部署时注入真实连接串；启动脚本里加校验。

### 4. 接口返回 `null`，但状态码是 200

**现象**：`/api/history` 返回 `null`，前端 `body["records"]` 报 `TypeError`。
**原因**：重构时误删了函数末尾的 `return {"records": ...}`。**服务照常启动，健康检查也通过。**
**定位**：pytest 立刻红了 3 个用例。
**教训**：健康检查通过不等于业务接口正常；有测试才能抓到这类"静默失败"。

### 5. `tar -xzf 包 | head` 解压不完整

**现象**：解压后 `index.html` 更新了，但 `_next/static/chunks/` 里的新文件没落地。
**原因**：`head` 读够行数就退出，关闭管道，`tar` 收到 SIGPIPE 被提前终止。
**修复**：解压时不要接 `head`。

