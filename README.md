# 求职面试官 Agent

上传简历 + 目标岗位 JD → AI 分析匹配度并给出改进建议 → 模拟面试官多轮追问 → 面经知识库（RAG）检索参考答法 → 全程会话留存。

## 状态

阶段 A · 工程化地基（进行中）

## 技术栈

- **后端**：Python 3.13 · FastAPI · SQLAlchemy 2.0 · SQLite（WAL）
- **AI**：LangChain · DeepSeek（对话）· 硅基流动 bge-m3（向量）· Chroma
- **前端**：原生 HTML + fetch + SSE
- **工程**：pytest · Docker · Nginx

## 目录结构

```
interview-agent/
├── app/                  # 应用主体（阶段 A2 建立）
│   ├── routers/          # 接口层：只做收参 → 调 service → 返回
│   ├── services/         # 业务层：真正的逻辑，可被 pytest 直接调用
│   ├── models/           # Pydantic 出入参 + ORM 表定义
│   ├── core/             # 配置、安全、日志、依赖注入
│   └── db/               # session 管理 + 迁移
├── tests/                # pytest 用例
├── docs/                 # 架构决策记录（ADR）
└── requirements.txt
```

## 快速开始

```bash
# 1. 建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 装依赖
pip install -r requirements.txt

# 3. 配密钥：复制 .env.example 为 .env，填入自己的 Key
copy .env.example .env

# 4. 起服务
uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000/docs 查看接口文档。

## 设计要点

1. **分层**：`routers` 只搬运，`services` 放逻辑 —— 逻辑可单测是分层的唯一理由。
2. **LLM 单一出口**：所有模型调用经 `services/llm.py`，超时/重试/限流/记账改一处生效。
3. **面试是状态机**：5 阶段 × 追问判定 × 最大追问 2 次，不是自由聊天。

## 已知限制
nihao
（随开发补充）
