## Context

AI Nexus 已完成 Phase 0+1，基础设施和图谱 CRUD 全部就绪。当前核心问题是**冷启动**——知识库为空，系统无法产生价值。

现有架构：
```
models → db → repos → services → api/mcp
                              ↗
                        proxy (mem0)
```

飞书知识库中有 6 篇完整设计文档，涵盖定位、数据库、MCP、Hook、审核工作流。朋友评审和 Graphify 竞品分析确认：**飞书知识注入必须提前到 Phase 1.5**。

技术约束：
- 后端：Python 3.11+, FastAPI
- 存储：SQLite（结构化）+ mem0（语义检索代理）
- AI API：Claude API（Anthropic SDK）用于知识抽取
- 协议：MCP (Model Context Protocol)
- 测试：pytest + pytest-asyncio
- 飞书 API：通过 lark-cli 或直接 HTTP 调用

## Goals / Non-Goals

**Goals:**
- 解决冷启动问题：从飞书文档批量导入知识，让知识库在第一天就有数据
- 实现 AI 知识抽取引擎：从任意文本（commit message、飞书文档）提取结构化业务知识
- 实现 Claude Code hooks 自动触发：pre-plan 注入 + pre-commit 校验
- 实现知识健康度监控：规则冲突检测、死规则发现、未覆盖风险
- 建立数据飞轮：PR 违规事件回写图谱，规则越用越准

**Non-Goals:**
- 不做通用代码理解（那是 Graphify 的赛道）
- 不做通用文档检索（那是 mem0/OpenViking 的赛道）
- 不做前端 UI 框架搭建（Phase 4 的事）
- 不做用户认证/权限系统（Phase 4 的事）
- 不做实时协作编辑
- 不自建向量数据库

## Decisions

### D1：知识抽取用 Claude API 而非本地模型

**选择**：使用 Anthropic Claude API 进行知识抽取
**备选**：本地 Ollama 模型、OpenAI API
**理由**：飞书文档已设计好提取 Prompt，Claude 的结构化输出能力最强。MVP 阶段成本可控（批量导入是一次性操作），后期可切换为更便宜的模型处理增量抽取。

### D2：飞书文档导入走 HTTP API 而非 lark-cli

**选择**：直接用 httpx 调用飞书 Open API
**备选**：shell 调用 lark-cli
**理由**：服务端运行需要稳定的 API 调用方式，lark-cli 适合 CLI 场景但不适合服务端集成。httpx 已经是项目依赖（mem0_proxy 用），不需要新增依赖。

### D3：extraction_service 是无状态的纯函数

**选择**：extraction_service 封装 Claude API 调用，输入文本，输出结构化 JSON
**备选**：带缓存的有状态服务
**理由**：保持和现有 repo/service 层一致的无状态设计。缓存由上层（审核工作流、批量导入进度）管理。

### D4：Claude Code hooks 用 shell 脚本触发 HTTP API

**选择**：hooks 配置为 shell 命令，调 AI Nexus REST API
**备选**：Python 脚本直接导入 ai_nexus 模块
**理由**：hooks 运行在 Claude Code 进程中，通过 HTTP API 调用保持了架构解耦。AI Nexus 作为独立服务运行，hooks 不需要知道内部实现。

### D5：知识 Lint 输出为 API 端点 + 可选周报

**选择**：`GET /api/lint/report` 返回 JSON，可选生成 Markdown 周报
**备选**：定时任务 + 飞书推送
**理由**：MVP 先提供 API，让调用方决定如何消费。飞书推送可以后加（Phase 4），不阻塞核心功能。

### D6：阶段划分调整

```
原计划：
Phase 0 → Phase 1 → Phase 2（Hook）→ Phase 3（知识抽取+Lint+飞轮）

调整后：
Phase 0 ✅ → Phase 1 ✅ → Phase 1.5（知识注入）→ Phase 2（Hook）→ Phase 3（Lint+飞轮）→ Phase 4（可视化）
```

**理由**：Phase 2 的 Hook 依赖知识库有数据，空库跑 Hook 毫无意义。先解决冷启动，Hook 才有价值。

## Risks / Trade-offs

**[冷启动仍可能失败]** → 飞书文档质量参差不齐，AI 抽取可能产生低质量候选项。缓解：审核工作流过滤，人工确认后才入库。

**[Claude API 成本]** → 批量导入飞书文档可能消耗大量 token。缓解：分批处理，提供 dry-run 模式预览抽取结果，让用户在消耗 API 额度前确认。

**[飞书 API 权限]** → 服务端访问飞书文档需要 app 凭证和用户授权。缓解：MVP 先用 user_access_token（lark-cli 已有认证），后期切换为 app 凭证。

**[hooks 调用延迟]** → pre-commit Hook 每次提交都调 HTTP API，可能增加提交延迟。缓解：本地缓存规则，只在缓存过期时调 API。目标延迟 < 500ms。

**[知识腐烂]** → 规则会过时，没有自动发现过时规则的机制。缓解：Phase 3 的 knowledge-lint 扫描，但 MVP 阶段依赖人工维护。

**[和 .cursor_rules / CLAUDE.md 的竞争]** → 轻量方案（markdown 文件）可能比整个服务更吸引团队。缓解：pre-commit 校验 + 审核工作流是 markdown 做不到的，这是差异化价值。
