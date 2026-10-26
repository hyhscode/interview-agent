# 求职面试官 Agent

[![CI](https://github.com/hyhscode/interview-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/hyhscode/interview-agent/actions/workflows/ci.yml)

上传简历和目标岗位 JD，AI 分析匹配度并给出修改建议；再扮演面试官追问几轮；结束后给一份评估。

个人项目，2027 届求职用。后端 FastAPI，前端原生 HTML/JS，对话用 DeepSeek，向量用硅基流动 bge-m3。

---

## 能做什么

| 功能 | 状态 |
| --- | --- |
| 注册 / 登录（JWT） | 已完成 |
| 上传简历 PDF，抽全文并用 LLM 解析成结构化数据 | 已完成 |
| 简历 + JD 匹配度分析（分数 / 缺口 / 修改建议） | 已完成 |
| 模拟面试（4 个阶段，多轮追问，结束给评估） | 已完成 |
| 面经知识库（向量 + BM25 混合检索） | 已完成 |
| 网页界面（登录 / 上传分析 / 面试对话） | 已完成 |
| 流式输出（SSE） | 未做 |
| Docker 部署 | 未做 |
| 检索效果评测 | 未做 |

当前 14 个接口，35 个测试。

---

## 快速开始

```bash
git clone https://github.com/hyhscode/interview-agent.git
cd interview-agent

python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
```

`.env` 里填两个 Key，都要自己申请：

- `DEEPSEEK_API_KEY`：https://platform.deepseek.com/api_keys
- `SILICONFLOW_API_KEY`：https://cloud.siliconflow.cn/account/ak

`JWT_SECRET_KEY` 模板里给了一个开发用的占位值，上线前换成随机串：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

建表并启动：

```bash
python -c "from app.db.session import Base, engine; import app.models; Base.metadata.create_all(engine)"
uvicorn app.main:app --reload --port 8000
```

- 网页：http://127.0.0.1:8000/app/
- 接口文档：http://127.0.0.1:8000/docs

跑测试：

```bash
python -m pytest -q
```

测试不调真实 LLM、不读写真实数据库，用假依赖和内存库，所以不花钱也不污染数据。

---

## 接口

```
POST   /auth/register                     注册
POST   /auth/login                        登录，返回 JWT
GET    /auth/me                           当前用户

POST   /resumes                           上传简历 PDF，抽文字 + LLM 解析
GET    /resumes/{id}                      取简历和解析结果
POST   /resumes/{id}/analysis             触发匹配分析，返回 202
GET    /resumes/{id}/analysis             查询分析结果

POST   /interviews                        开始面试，返回第一个问题
POST   /interviews/{id}/answer            提交回答，返回下一个问题
POST   /interviews/{id}/finish            结束并生成评估
GET    /interviews/{id}                   取完整对话

POST   /kb/documents                      上传面经文档（txt / md）
GET    /kb/search?q=&top_k=               检索面经

GET    /healthz                           健康检查
```

---

## 目录

```
app/
├── main.py                应用入口，中间件（request_id / 计时 / 异常兜底）
├── core/
│   ├── config.py          读 .env 成 Settings 对象
│   ├── security.py        密码哈希、JWT 签发校验
│   └── deps.py            get_current_user，从 token 认出用户
├── db/session.py          连接池、会话工厂、get_db
├── models/                表结构（users / resumes / analyses / interviews / kb）
├── schemas/               接口出入参
├── services/              业务逻辑，不依赖 HTTP
│   ├── auth.py            查重、建用户、验密码
│   ├── pdf.py             PDF 抽文字
│   ├── llm.py             LLM 调用的唯一出口
│   ├── resume_parser.py   文本 → 结构化 JSON
│   ├── analyzer.py        简历 × JD → 分析结果
│   ├── embeddings.py      文本 → 向量
│   ├── bm25.py            关键词打分
│   ├── kb.py              切块、入库、混合检索
│   ├── interview.py       会话存储
│   └── interview_state.py 面试状态机
└── routers/               接口层
static/index.html          前端单页
tests/                     35 个用例
docs/api-contract.md       接口契约
```

依赖方向单向：`routers → services → models → db`，`core` 被所有层使用。

`services` 里不 import `Request` 和 `Response`，所以业务逻辑能被 pytest 直接调用，不用起服务。

---

## 几个设计决定

**配置缺了直接启动失败。**
`Settings` 的必填字段没有默认值，读不到就抛 `ValidationError`。部署时立刻发现，比上线后某个接口 500 好查。

**数据库字段叫 `hashed_password`，不叫 `password`。**
写代码时看到这个名字，就不会往上存明文。

**越权访问返回 404，不返回 403。**
403 等于告诉对方“这条记录存在，只是不属于你”。404 什么都不泄露。

**归属条件写在 SQL 的 WHERE 里，不是查出来再判断。**
`where(id == ?, user_id == ?)` 一次查完。查出来再判断是两处逻辑，以后加缓存容易漏。

**分析接口拆成“触发 + 查询”两个。**
LLM 分析要十几秒，合成一个接口会让请求一直挂着，网一断就白等。拆开后 POST 返回 202，前端轮询 GET。

**面试流程用自研状态机，没用 LangGraph。**
4 个阶段、每阶段最多问 3 次，60 行就够，而且每一段都能单测。模型只负责“这句话怎么问”，问哪个阶段、要不要结束由代码决定。

**向量检索没上 Chroma。**
几千个块用 numpy 算一遍余弦也就几十毫秒，少一个依赖。数据量到十万级再换索引。

---

## 已知问题

- 扫描版 PDF 抽不出文字（需要 OCR），会返回 400
- 面经检索只用一份测试文档调过切块参数，没做系统评测
- 单机 SQLite，没做并发压测
- 没有 Docker 和部署脚本
- 前端没做移动端适配

---

## 开发进度

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| A | 分层架构、配置、中间件、测试、CI | 完成 |
| B | 用户系统、简历解析、匹配分析、会话、RAG、面试 | 完成 |
| C | 前端页面 | 完成（SSE 未做） |
| D | Docker、部署、评测报告 | 未开始 |
