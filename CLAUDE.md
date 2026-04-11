# CLAUDE.md — AI Nexus 项目指南

## 项目定位

AI Nexus 是业务知识治理层，不是通用记忆系统。核心三件事：
1. 业务知识图谱（实体+关系+规则的 CRUD + D3.js 可视化）
2. 开发流程 Hook（pre_plan 注入 + pre_commit 校验 + post_task 抽取）
3. 知识审核工作流（AI 抽取 + 人工审核 + 自动入库）

## 技术约束

- 后端：Python 3.11+, FastAPI
- 存储：SQLite（结构化）+ Qdrant（向量）
- LLM：Anthropic SDK（支持兼容 API 如 MiniMax）
- 协议：MCP (Model Context Protocol)
- 不自建向量数据库层，不做通用记忆管理，不做文档库

## 代码规范

- 遵循 PEP 8
- 所有 public 函数需要 type hints
- 测试框架：pytest
- 提交前运行 `pytest` 和 `ruff check`

## 数据库

4 张核心表：entities, relations, rules, knowledge_audit_log
详见 docs/feishu/02-数据库设计.md

## MCP 工具

5 个核心工具：search_entities, search_rules, get_business_context, validate_against_rules, submit_knowledge_candidate
详见 docs/feishu/04-MCP-Server设计.md

## 当前阶段

Phase 3 完成 — 知识飞轮已闭环

## 知识飞轮（Knowledge Flywheel）

```
commit → AI 抽取 → 人工审核 → 知识入库 → hook 可查 → 更好的代码 → commit
```

### 触发方式

1. **Cold Start（冷启动）**：`POST /api/cold-start` — 根据领域描述生成初始知识框架
2. **Post-Task Hook**：`POST /api/hooks/post-task` — 任务完成后自动抽取知识
3. **Git Post-Commit**：`.git/hooks/post-commit` — 提交后自动抽取
4. **MCP 工具**：`submit_knowledge_candidate` — 手动提交候选
5. **Console 导入**：`/console/imports` — Web 界面批量导入

### 审核入库

- 审核页面：`http://localhost:8000/console/audit`
- 批准时自动入库：`ExtractionService.ingest_candidate()` 将候选项写入 entities/relations/rules 表
- 去重机制：按 `name + domain` 检查，已有则更新

### 规则校验

- Pre-Plan：`POST /api/hooks/pre-plan` — 根据任务关键词检索相关实体和规则
- Pre-Commit：`POST /api/hooks/pre-commit` — 校验变更是否违反业务规则
- Git Commit-Msg：`.git/hooks/commit-msg` — 提交前自动校验（warning only）

## 开发流程 Hook

每次开始任务前，必须调用 MCP 工具 `get_business_context` 注入业务上下文：
- 提取 task 描述中的关键词
- 调用 `get_business_context(task_description, keywords=[...])` 获取相关实体和规则
- 阅读返回的规则，确保变更不违反 critical 级别约束

完成代码修改后：
- 如果发现新的业务规则或实体，调用 `submit_knowledge_candidate` 提交候选
- 在 http://localhost:8000/console/audit 审核确认

## Git Hooks

项目配置了两个 git hooks：
- `commit-msg`：提交前自动校验 commit message 是否违反业务规则（warning only）
- `post-commit`：提交后自动调用 LLM 抽取知识，提交为待审核候选

安装方式：`bash scripts/install-hooks.sh`

## Web Console

管理界面运行在 `http://localhost:8000/console/`，包含：
- 仪表板：系统概览
- 实体/规则/关系管理：CRUD 操作
- 知识图谱：D3.js 交互式可视化（`/graph`）
- 审核工作流：AI 抽取候选项的人工审核
- 知识 Lint：数据质量检查
- 导入管理：批量知识导入
- 系统设置

## LLM 配置

通过环境变量配置（`.env` 文件）：
- `AI_NEXUS_ANTHROPIC_API_KEY`：API 密钥
- `AI_NEXUS_ANTHROPIC_BASE_URL`：API 地址（支持兼容代理）
- `AI_NEXUS_LLM_MODEL`：模型名称
- `AI_NEXUS_LLM_MAX_TOKENS`：最大 token 数
