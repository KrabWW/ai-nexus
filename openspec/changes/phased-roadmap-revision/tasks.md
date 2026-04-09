## 1. Phase 1.5 — AI 知识抽取引擎

- [x] 1.1 添加 `anthropic` SDK 到 pyproject.toml 依赖
- [x] 1.2 创建 `src/ai_nexus/extraction/extraction_service.py`：封装 Claude API 调用，输入文本输出结构化 JSON（entities/relations/rules）
- [x] 1.3 实现提取 Prompt（飞书文档已设计好的版本），支持 domain_hint 参数
- [x] 1.4 定义 `ExtractionResult` Pydantic 模型（entities/relations/rules 列表，每项含 name/type/domain/confidence/description）
- [x] 1.5 实现 Claude API 响应解析与 schema 校验（容错处理：响应不符合预期格式时尝试修复或返回空结果）
- [x] 1.6 编写 `tests/test_extraction_service.py`：mock Claude API，测试文本→结构化输出、无业务知识时返回空、domain_hint 效果
- [x] 1.7 提交：`feat(extraction): add ExtractionService with Claude API knowledge extraction`

## 2. Phase 1.5 — 飞书文档批量导入

- [x] 2.1 添加飞书 API 配置到 `config.py`（`feishu_app_id`、`feishu_app_secret`、`feishu_base_url`）
- [x] 2.2 创建 `src/ai_nexus/proxy/feishu_proxy.py`：封装飞书 Open API 调用（获取知识空间文档列表、读取文档内容），复用 httpx
- [x] 2.3 创建 `src/ai_nexus/services/ingest_service.py`：编排飞书读取 → 抽取引擎 → 审核工作流，支持 dry_run 模式
- [x] 2.4 创建 `src/ai_nexus/db/migrations/002_ingest_tracking.sql`：`ingest_tracking` 表（space_id, doc_token, content_hash, status, last_imported_at）
- [x] 2.5 添加 REST API 端点 `POST /api/ingest/feishu`（批量导入）和 `POST /api/ingest/document`（单文档导入）
- [x] 2.6 实现增量导入：对比 content_hash 跳过未变更文档，重新处理已变更文档
- [x] 2.7 编写 `tests/test_ingest_service.py`：mock feishu_proxy 和 extraction_service，测试批量导入、dry_run、增量跳过
- [x] 2.8 提交：`feat(ingest): add Feishu document batch import pipeline with extraction engine`

## 3. Phase 1.5 — 验证与集成

- [x] 3.1 端到端测试：从飞书 AI Nexus 知识库实际导入文档，验证实体/关系/规则候选提交到审核工作流
- [x] 3.2 在 `/api/audit/pending` 审核候选项，确认 approved 后正确入库
- [x] 3.3 通过 `POST /api/search` 搜索已入库的知识，验证可查询
- [x] 3.4 全量测试 `pytest tests/ -v` + lint `ruff check src/`
- [x] 3.5 提交：`feat(ingest): e2e validation with Feishu AI Nexus wiki`

## 4. Phase 2 — Claude Code Hooks

- [x] 4.1 创建 `src/ai_nexus/hooks/pre_plan.py`：读取任务上下文 → 调 `POST /api/hooks/pre-plan` → 输出 system reminder
- [x] 4.2 创建 `src/ai_nexus/hooks/pre_commit.py`：读取 staged changes → 调 `POST /api/hooks/pre-commit` → 输出违规警告或通过
- [x] 4.3 实现 hooks 超时处理（5s 超时，不阻塞 commit）和服务不可用时的静默降级
- [x] 4.4 实现 `ai-nexus install-hooks` CLI 命令：生成 `.claude/settings.json` hooks 配置
- [x] 4.5 编写 `tests/test_hooks.py`：mock HTTP API，测试 pre_plan 注入、pre_commit 校验、超时降级
- [x] 4.6 在真实 Claude Code 会话中测试 hooks 触发（pre-plan 注入业务上下文、pre-commit 检测违规）
- [x] 4.7 全量测试 + lint
- [x] 4.8 提交：`feat(hooks): add Claude Code pre-plan and pre-commit hook scripts`

## 5. Phase 3 — 知识 Lint

- [x] 5.1 创建 `src/ai_nexus/services/lint_service.py`：规则冲突检测（同 domain 内矛盾规则配对发现）
- [x] 5.2 实现死规则检测：30天+无审核日志引用的 approved 规则标记为潜在死规则
- [x] 5.3 实现覆盖缺口检测：有实体但无规则的 domain 标记为未覆盖风险
- [x] 5.4 添加 `GET /api/lint/report` 端点（JSON 格式）和 `?format=markdown` 支持
- [x] 5.5 编写 `tests/test_lint_service.py`：构造冲突规则、死规则、覆盖缺口场景
- [x] 5.6 全量测试 + lint
- [x] 5.7 提交：`feat(lint): add knowledge health scanning with conflict, dead-rule, and coverage detection`

## 6. Phase 3 — 数据飞轮

- [x] 6.1 创建 `src/ai_nexus/db/migrations/003_violation_events.sql`：`violation_events` 表（rule_id, change_description, resolution, created_at）
- [x] 6.2 修改 pre-commit Hook：违规时记录 violation_event（resolution: fixed/suppressed/ignored）
- [x] 6.3 实现规则置信度自动提升：成功捕获违规 → confidence += 0.02（上限 1.0）
- [x] 6.4 实现违规模式检测：相似未捕获违规 ≥3 次时自动生成规则候选
- [x] 6.5 添加 `GET /api/violations/stats` 端点（30天统计：per-rule 违规数、修复率、平均修复时间）
- [x] 6.6 编写 `tests/test_flywheel.py`：测试事件记录、置信度提升、候选生成
- [x] 6.7 全量测试 + lint
- [x] 6.8 提交：`feat(flywheel): add violation event capture, confidence boost, and auto rule candidate generation`

## 7. Phase 4 — 图谱可视化

- [x] 7.1 搭建前端基础：在项目中添加静态文件服务（FastAPI StaticFiles），创建 `static/` 目录
- [x] 7.2 实现力导向图渲染（D3.js）：实体为节点、关系为边，按 domain 着色
- [x] 7.3 实现 domain 过滤器：选择 domain 后只显示该 domain 的实体和关系
- [x] 7.4 实现实体详情面板：点击节点显示属性、关联规则、相连实体
- [x] 7.5 实现规则严重度可视化：critical 红色边框、warning 黄色、info 蓝色
- [x] 7.6 实现图谱搜索：输入关键词高亮匹配节点、暗化非匹配节点
- [x] 7.7 添加 `GET /graph` 路由，渲染可视化页面
- [x] 7.8 提交：`feat(viz): add D3.js interactive graph visualization with domain filter and search`

## 8. 补丁 — 缺口修复

- [x] 8.1 修复 `ai-nexus install-hooks` CLI 入口：在 pyproject.toml 添加 console_scripts 入口，使 `ai-nexus install-hooks` 命令可直接执行
- [x] 8.2 修复图谱 domain 过滤器：过滤某 domain 时，跨 domain 的连接实体应显示为半透明淡色（而非完全不透明）

## 9. 设计文档对齐 — MCP 工具完善

- [x] 9.1 修复 MCP `submit_knowledge_candidate` 空壳：接入 audit_repo 实际写入审核工作流（当前只返回 JSON 消息）
- [x] 9.2 添加 MCP `get_session_ctx` mem0 代理工具：在 MCP Server 暴露 mem0 会话记忆代理，Claude Code 只看一个 MCP 入口（飞书 01-竞品分析要求）
- [x] 9.3 修复 `validate_against_rules` 只检查 critical：应检查所有 severity 级别，返回分级警告（error/warning/info）
- [x] 9.4 添加 `POST /api/search/reindex` 端点：架构文档 §12 明确列出但未实现
- [x] 9.5 添加 MCP 图谱遍历工具：`get_neighbors(entity_id)` 和 `shortest_path(from_id, to_id)`（Graphify 对标）

## 10. Graphify 对标 — 增强特性

- [x] 10.1 添加知识来源可信度标签：每条抽取结果标注 EXTRACTED（直接提取）/ INFERRED（推断）/ AMBIGUOUS（待确认），区别于 confidence 分数
- [x] 10.2 实现 God nodes 分析：自动识别图谱中度最高的关键节点，输出 "哪些概念是一切连接的枢纽"
- [x] 10.3 实现 Surprising connections 发现：跨 domain 的意外关联，按复合评分排序（类似 Graphify 的 surprising connections）
- [x] 10.4 添加 Git hooks 集成：post-commit/post-checkout 自动触发知识图谱更新（`graphify hook install` 模式）
- [x] 10.5 实现 Leiden 社区发现：自动聚类图谱节点，不依赖 embedding，基于图拓扑边密度

## 11. Phase 5 — Web Console

- [x] 11.1 搭建 Web Console 基础：基于 FastAPI + Jinja2 模板或 React SPA，统一管理界面入口
- [x] 11.2 实现实体管理页面：列表 + 搜索 + 新建 + 编辑 + 删除，支持按 domain 过滤
- [x] 11.3 实现规则管理页面：列表 + 搜索 + severity 过滤 + 新建 + 编辑，显示置信度和来源
- [x] 11.4 实现关系管理页面：可视化关系列表 + 新建 + 删除，显示源/目标实体
- [x] 11.5 实现审核工作流页面：候选项列表 → approve/reject 操作 + 审核历史记录
- [x] 11.6 实现知识 Lint 仪表盘：展示冲突规则、死规则、覆盖缺口的可视化报告
- [x] 11.7 实现导入管理页面：飞书空间导入 + 单文档导入 + 导入历史追踪（ingest_tracking）
- [x] 11.8 实现系统设置页面：配置管理 + 健康检查 + mem0/OpenViking 连接状态
- [x] 11.9 提交：`feat(console): add Web Console for knowledge graph management`

## 12. Graphify 功能性对比 — 深度分析

- [ ] 12.1 分析 Graphify 源码架构（NetworkX + Leiden + tree-sitter），提取可复用设计模式
- [ ] 12.2 对比 Graphify 抽取引擎 vs AI Nexus ExtractionService，优化提取 Prompt 和容错机制
- [ ] 12.3 对比 Graphify 可视化 (vis.js) vs AI Nexus 可视化 (D3.js)，评估是否需要迁移或增强
- [ ] 12.4 评估 Graphify 的 MCP Server 实现，改进 AI Nexus MCP 工具设计
- [ ] 12.5 评估 Graphify 增量更新机制 (SHA256 cache)，完善 AI Nexus 的通用增量导入

## 13. 里程碑验证

- [x] 8.1 Phase 1.5 里程碑：飞书知识库文档已导入，审核通过的知识可通过 MCP 搜索到
- [x] 8.2 Phase 2 里程碑：Claude Code pre-plan 自动注入业务上下文 + pre-commit 拦截违规变更
- [x] 8.3 Phase 3 里程碑：知识 Lint 报告可生成 + 数据飞轮自动运行
- [x] 8.4 Phase 4 里程碑：图谱可视化页面可交互浏览
