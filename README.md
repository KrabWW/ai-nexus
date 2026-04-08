# AI Nexus

**AI 业务知识治理层** — 让 AI 像资深员工一样懂业务规则。

AI Nexus 把企业特有的业务规则和实体关系嵌入 AI 开发循环，解决"AI 写代码但不懂业务"的问题。它不与通用记忆工具（OpenViking/mem0）竞争，而是作为下游业务知识治理层，复用它们的基础设施。

## 做什么

| 模块 | 说明 |
|------|------|
| **业务知识图谱** | 实体 + 关系 + 规则的结构化 CRUD，支持语义检索 |
| **开发流程 Hook** | pre_plan 注入业务上下文，pre_commit 校验业务规则 |
| **知识审核工作流** | AI 自动抽取知识候选项，人工审核后入库 |

## 不做什么

- 不自建向量数据库层（用 Qdrant）
- 不做通用 Agent 记忆管理（OpenViking 的赛道）
- 不做文档库（飞书/Confluence 已经做了）

## 技术栈

- Python 3.11+ / FastAPI
- SQLite（结构化图谱） + Qdrant（语义检索）
- MCP (Model Context Protocol)
- Claude Code hooks 集成

## 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 启动 Qdrant
docker compose up -d qdrant

# 初始化数据库
python scripts/init_db.py

# 启动 MCP Server
python -m ai_nexus.mcp.server
```

## 项目结构

```
src/ai_nexus/
├── graph/          # 业务知识图谱（实体/关系/规则 CRUD）
├── hooks/          # 开发流程 Hook（pre_plan/pre_commit）
├── extraction/     # AI 知识抽取引擎
├── db/             # 数据库层（SQLite + Qdrant）
└── mcp/            # MCP Server
```

## MVP 路线图

| Phase | 时间 | 目标 | 里程碑 |
|-------|------|------|--------|
| 0 | 2 周 | 基础设施接入 | MCP 空工具调通 |
| 1 | 4 周 | 业务知识图谱 MVP | Claude Code 查到真实业务规则 |
| 2 | 3 周 | 开发流程 Hook | AI 因业务规则被纠正的 demo |
| 3 | 3 周 | 知识审核工作流 | AI 发现+人工确认的规则入库 |

## License

Apache License 2.0
