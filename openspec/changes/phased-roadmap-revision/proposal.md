## Why

AI Nexus 已完成 Phase 0+1（基础设施 + 图谱 CRUD + MCP + REST API），但面临**冷启动死穴**：知识库是空的，系统无法产生价值。朋友评审和 Graphify 竞品分析一致指出：飞书知识自动注入的优先级必须从 Phase 3 提到 Phase 1.5。同时，原路线图的阶段划分需要根据实际反馈重新调整，确保每个阶段结束时都有可演示的价值产出。

## What Changes

- **新增 Phase 1.5：知识注入（冷启动破解）** — 飞书文档编译管道 + AI 抽取引擎 + 审核工作流对接，让知识库从空变满
- **Phase 2 调整：开发流程 Hook** — 在知识库有数据的基础上，配置 Claude Code hooks 实现真正的 pre-plan/pre-commit 自动触发
- **Phase 3 重新定义：增强与飞轮** — 知识 Lint（规则冲突检测、死规则扫描）+ 数据飞轮（PR 违规事件回写图谱）+ 知识健康度周报
- **Phase 4 新增：团队协作与可视化** — 多用户权限、图谱可视化、管理界面
- **移除原 Phase 3 中的飞书抽取** — 已提前到 Phase 1.5

## Capabilities

### New Capabilities

- `feishu-ingest-pipeline`: 飞书文档批量读取 + LLM 编译为结构化知识（实体/关系/规则）+ 候选项提交到审核工作流
- `extraction-engine`: 通用 AI 知识抽取引擎（Claude API 调用 + 结构化输出），支持从任意文本（commit message、PR、文档）提取业务知识
- `claude-code-hooks`: Claude Code hooks 配置（.claude/settings.json），实现 pre-plan 自动注入业务上下文 + pre-commit 自动校验业务规则
- `knowledge-lint`: 知识健康度扫描（规则冲突检测、死规则发现、未覆盖风险提示）+ 周报生成
- `data-flywheel`: PR 违规事件自动回写图谱，加强规则置信度，生成新规则候选项
- `graph-visualization`: 基于 D3.js 的图谱可视化界面

### Modified Capabilities

（无已有 spec 需要修改，这是首次建立 OpenSpec 规范）

## Impact

- **代码**：新增 `extraction/` 模块（extraction_service.py）、`hooks/` 脚本（pre_plan.py, pre_commit.py）
- **API**：新增批量导入端点 `POST /api/ingest/feishu`，新增知识健康度端点 `GET /api/lint/report`
- **依赖**：新增 `anthropic` SDK 依赖（AI 抽取需要 Claude API）
- **配置**：新增 `AI_NEXUS_ANTHROPIC_API_KEY` 环境变量（必填），新增飞书 API 凭证配置
- **基础设施**：飞书 API 访问权限（lark-cli 或直接 API 调用）
- **现有测试**：需要为 extraction_service 添加 mock Claude API 的测试
