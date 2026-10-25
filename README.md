# 求职面试官 Agent

[![CI](https://github.com/hyhscode/interview-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/hyhscode/interview-agent/actions/workflows/ci.yml)

> **上传简历 + 目标岗位 JD → AI 分析匹配度并逐条给建议 → 模拟面试官多轮追问 → 面经知识库检索参考答法。**

给大学生用的「面试前最后一次彩排」：先告诉你简历差在哪，再让你被追问一遍。

**当前状态**：开发中（阶段 B · 核心功能）。基础设施已完成，业务功能逐个接入。

---

## 现在能做什么

| 能力 | 状态 |
|---|---|
| 用户注册（邮箱 + argon2 密码哈希） | ✅ 已完成 |
| 健康检查 `/healthz` + 全链路 `request_id` 日志 | ✅ 已完成 |
| 统一 JSON 错误响应（含 request_id 便于排查） | ✅ 已完成 |
| 自动化测试（6 个用例）+ GitHub Actions CI | ✅ 已完成 |
| 登录 / JWT 认证 | 🚧 进行中 |
| 简历与 JD 解析（PDF → 结构化） | ⬜ 待开发 |
| 匹配度分析（LLM 结构化输出） | ⬜ 待开发 |
| 面试会话管理（多轮 + 历史压缩） | ⬜ 待开发 |
| 面经知识库（RAG + 重排） | ⬜ 待开发 |
| 模拟面试状态机（阶段 + 追问策略） | ⬜ 待开发 |
| 前端页面 + SSE 流式输出 | ⬜ 待开发 |

---

## 架构

```
浏览器 ──HTTP / Bearer JWT──► FastAPI
                                │
        ┌───────────────────────┼─────────────────────┐
        ▼                       ▼                     ▼
    routers/                services/              core/
    （门面：收参数）          （业务逻辑）            （配置·安全·日志）
        │                       │
        └───────────┬───────────┘
                    ▼
              models/（表结构）──► db/（会话管理）──► SQLite

    外部依赖：DeepSeek（对话）· 硅基流动 bge-m3（向量）· Chroma（向量库）
```

**三条分层纪律**（这个项目最想证明的东西）：

1. **`routers` 只做收参数 → 调 service → 返回**，不写业务逻辑、不直接查库
2. **`services` 不知道 HTTP 存在**（不 import `Request`/`Response`），所以能被 `pytest` 直接调用
3. **`models` 只描述表结构**，不写判断和计算

---

## 技术选型与理由

| 层 | 选型 | 为什么 |
|---|---|---|
| Web 框架 | FastAPI | 原生 async（SSE 流式需要）、自动生成 OpenAPI 文档、依赖注入便于测试 |
| 数据校验 | Pydantic v2 | 出入参即契约；校验写在 schema 里会自动进文档，前端可见 |
| ORM | SQLAlchemy 2.0 | 换数据库只改连接串；`Mapped[...]` 带类型提示 |
| 数据库 | SQLite（WAL） | 单机零运维；代码里不留方言，随时可换 PostgreSQL |
| 密码 | pwdlib（argon2id） | 抗 GPU 暴力破解，每次哈希自带随机盐；不用已停止维护的 passlib |
| 测试 | pytest + `dependency_overrides` | 用假配置、假依赖，不依赖真实 `.env` 和真实数据库 |
| 部署 | Docker + Nginx | 一次构建到处跑；Nginx 负责 HTTPS 与反向代理 |

---

## 快速开始

```bash
# 1. 建虚拟环境
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux

# 2. 装依赖
pip install -r requirements.txt

# 3. 配密钥（复制模板，填入自己的 Key）
copy .env.example .env           # macOS/Linux: cp .env.example .env

# 4. 建表 + 启动
python -c "from app.db.session import Base, engine; import app.models; Base.metadata.create_all(engine)"
uvicorn app.main:app --reload --port 8000
```

打开 http://127.0.0.1:8000/docs ，可以直接在网页上试所有接口。

跑测试：

```bash
python -m pytest -q
```

---

## 项目结构

```
interview-agent/
├── app/
│   ├── core/          # 配置、安全（密码哈希）、日志
│   ├── db/            # 数据库连接与会话管理
│   ├── models/        # SQLAlchemy 表定义
│   ├── schemas/       # Pydantic 接口出入参
│   ├── services/      # 业务逻辑（可单测）
│   ├── routers/       # 接口层
│   └── main.py        # 应用入口 + 中间件
├── tests/             # pytest 用例 + conftest
├── docs/
│   └── api-contract.md    # 14 个接口的契约与三处关键设计决策
└── requirements.txt
```

---

## 几个设计取舍

**① 为什么缺配置时宁可启动失败**
`Settings` 里必填字段不设默认值，缺了直接 `ValidationError` 起不来。
理由：宁可部署时立刻炸，也不要等用户点了按钮才 500 —— **早期报错远比运行时炸便宜。**

**② 为什么密码字段叫 `hashed_password` 而不是 `password`**
字段名本身就是一道防线：从表结构上杜绝「不小心存明文」。

**③ 为什么先写接口契约再写代码**
`docs/api-contract.md` 里 14 个接口先定下来，前后端才能并行，避免字段名对不上返工。

**④ 为什么面试流程用自研状态机而不是 LangGraph**
5 个阶段、max_followups=2，手写 60 行足够，而且每一步都能单测；引入编排框架会增加解释成本，不增加这个规模下的收益。

---

## 已知限制（诚实清单）

- 扫描版 PDF 抽不出文字，暂不支持
- 单机部署，未做水平扩展
- 面经检索的评测集只有 20 题，指标有波动
- 目前没有前端界面，只能用 `/docs` 调试

---

## 开发进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | Git / 分层 / 配置 / 测试 / CI | ✅ 完成 |
| B | 核心功能（用户系统 → 解析 → 分析 → 会话 → RAG → 面试） | 🚧 B1 进行中 |
| C | SSE 流式 + 前端页面 | ⬜ 未开始 |
| D | Docker 部署 + 评测报告 + 文档 | ⬜ 未开始 |
