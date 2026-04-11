# AI Nexus

**AI 业务知识治理层** — 让 AI 像资深员工一样懂业务规则。

AI Nexus 把企业特有的业务规则和实体关系嵌入 AI 开发循环，解决"AI 写代码但不懂业务"的问题。

## 核心能力

| 模块 | 说明 |
|------|------|
| **业务知识图谱** | 实体 + 关系 + 规则的结构化 CRUD，D3.js 可视化 |
| **开发流程 Hook** | pre_plan 注入上下文、pre_commit 校验规则、post_task 抽取知识 |
| **知识审核工作流** | AI 自动抽取 + 人工审核 + 自动入库，形成知识飞轮 |

## 知识飞轮

```
commit → AI 抽取 → 人工审核 → 知识入库 → hook 可查 → 更好的代码 → commit
```

知识自动增长：每次提交代码都可能产生新的业务知识，经人工确认后进入图谱，下次开发时自动注入。

## 快速开始

### 1. 安装

```bash
# 克隆项目
git clone https://github.com/KrabWW/ai-nexus.git
cd ai-nexus

# 安装依赖
pip install -e ".[dev]"
```

### 2. 配置

创建 `.env` 文件（项目根目录）：

```env
# LLM 配置（支持 Anthropic 兼容 API）
AI_NEXUS_ANTHROPIC_API_KEY=your-api-key
AI_NEXUS_ANTHROPIC_BASE_URL=https://api.anthropic.com    # 或兼容代理地址
AI_NEXUS_LLM_MODEL=claude-sonnet-4-20250514              # 或其他兼容模型
AI_NEXUS_LLM_MAX_TOKENS=4096
```

> 没有 API Key 也能运行，知识抽取功能会优雅降级（返回空结果）。

### 3. 启动服务

```bash
python -m uvicorn ai_nexus.main:app --host 0.0.0.0 --port 8000
```

启动后访问：
- Web Console: http://localhost:8000/console/
- 知识图谱: http://localhost:8000/console/graph
- API 文档: http://localhost:8000/docs

### 4. 冷启动（导入初始知识）

首次使用时，通过冷启动快速建立知识框架：

```bash
curl -X POST http://localhost:8000/api/cold-start \
  -H 'Content-Type: application/json' \
  -d '{
    "domain": "电商系统",
    "description": "在线商城，包含用户注册、商品管理、订单处理、支付流程、物流配送"
  }'
```

AI 会自动生成一批实体、规则和关系候选项。前往 http://localhost:8000/console/audit 审核确认。

### 5. 安装 Git Hooks

Git Hooks 让每次提交自动触发知识校验和抽取：

```bash
bash scripts/install-hooks.sh
```

安装后：
- `git commit` 提交前自动校验业务规则（不阻塞，仅警告）
- `git commit` 提交后自动抽取知识，提交为待审核候选

卸载：`rm .git/hooks/commit-msg .git/hooks/post-commit`

## Web Console 使用

管理界面运行在 http://localhost:8000/console/，包含以下功能：

| 页面 | 路径 | 功能 |
|------|------|------|
| 仪表板 | `/console/` | 系统概览、数据统计 |
| 实体管理 | `/console/entities` | 业务实体 CRUD |
| 规则管理 | `/console/rules` | 业务规则 CRUD（支持 severity 分级） |
| 关系管理 | `/console/relations` | 实体间关系 CRUD |
| 知识图谱 | `/console/graph` | D3.js 交互式图谱可视化 |
| 审核工作流 | `/console/audit` | 审核待批准的知识候选项 |
| 知识 Lint | `/console/lint` | 数据质量检查 |
| 导入管理 | `/console/imports` | 批量知识导入 |

### 审核工作流

AI 抽取的知识候选项需要人工审核：

1. 访问 **审核工作流** 页面
2. 查看待审核项中的实体、规则、关系
3. 点击 **批准** → 候选项自动写入知识图谱
4. 点击 **拒绝** → 丢弃该候选项

批准后知识会按 `name + domain` 自动去重，已存在则更新。

## API 使用

### 知识图谱 CRUD

```bash
# 创建实体
curl -X POST http://localhost:8000/api/entities \
  -H 'Content-Type: application/json' \
  -d '{"name": "订单", "type": "business_object", "domain": "交易", "description": "用户购买请求"}'

# 查询实体
curl http://localhost:8000/api/entities?domain=交易

# 创建规则
curl -X POST http://localhost:8000/api/rules \
  -H 'Content-Type: application/json' \
  -d '{"name": "订单状态单向流转", "severity": "critical", "domain": "交易", "description": "订单状态只能单向流转，禁止回退"}'
```

### 开发流程 Hook

#### Pre-Plan（开发前注入上下文）

开始编码前，获取相关业务知识：

```bash
curl -X POST http://localhost:8000/api/hooks/pre-plan \
  -H 'Content-Type: application/json' \
  -d '{"task_description": "修改订单退款逻辑", "keywords": ["订单", "退款"]}'
```

返回相关实体和规则，critical 级别规则是硬约束，不可违反。

#### Pre-Commit（提交前校验）

校验代码变更是否违反业务规则：

```bash
curl -X POST http://localhost:8000/api/hooks/pre-commit \
  -H 'Content-Type: application/json' \
  -d '{"change_description": "删除已支付订单", "affected_entities": ["订单", "支付"]}'
```

返回 errors（critical 违规）、warnings（warning 提示）、passed（是否通过）。

#### Post-Task（完成后抽取知识）

任务完成后自动从描述中抽取知识：

```bash
curl -X POST http://localhost:8000/api/hooks/post-task \
  -H 'Content-Type: application/json' \
  -d '{"task_description": "新增商品评分功能，用户只能对已购买商品评分一次"}'
```

自动提取实体和规则，提交为待审核候选。

### 图谱可视化数据

```bash
# 获取图谱数据
curl http://localhost:8000/api/graph/data

# 高连接度节点
curl http://localhost:8000/api/graph/god-nodes?limit=10

# 跨域意外连接
curl http://localhost:8000/api/graph/surprising-connections?limit=10

# Leiden 社区检测
curl http://localhost:8000/api/graph/communities?resolution=1.0
```

## Claude Code 集成

AI Nexus 提供 Claude Code Skill，自动在开发流程中注入业务上下文。

Skill 位置：`.claude/skills/knowledge-hooks/SKILL.md`

### 工作流程

1. **开始任务时**：自动调用 `get_business_context`，获取相关实体和规则
2. **编码过程中**：遵守 critical 规则约束
3. **完成任务后**：如发现新知识，调用 `submit_knowledge_candidate` 提交
4. **Git 提交时**：hooks 自动触发校验和抽取

### MCP 工具

AI Nexus 暴露 5 个 MCP 工具供 AI 助手使用：

| 工具 | 说明 |
|------|------|
| `search_entities` | 搜索业务实体 |
| `search_rules` | 搜索业务规则 |
| `get_business_context` | 获取完整业务上下文（Pre-Plan 用） |
| `validate_against_rules` | 校验变更是否违反规则（Pre-Commit 用） |
| `submit_knowledge_candidate` | 提交知识候选项（Post-Task 用） |

## 项目结构

```
src/ai_nexus/
├── api/                    # FastAPI 路由
│   ├── router.py           # REST API（CRUD + hooks + 审核）
│   ├── console_router.py   # Web Console 页面
│   ├── graph_router.py     # 图谱可视化
│   └── dependencies.py     # 依赖注入
├── db/                     # 数据库层
│   ├── sqlite.py           # SQLite 连接 + 迁移
│   └── migrations/         # SQL 迁移脚本
├── models/                 # Pydantic 数据模型
├── repos/                  # 数据访问层
├── services/               # 业务逻辑
│   ├── graph_service.py    # 图遍历 + 上下文组装
│   ├── query_service.py    # 统一查询路由
│   ├── extraction_service.py  # LLM 知识抽取
│   └── flywheel_service.py # 规则校验
├── prompts/                # LLM Prompt 模板
├── mcp/                    # MCP Server
└── config.py               # 配置管理

templates/                  # Jinja2 模板（Web Console）
static/                     # 静态资源（CSS/JS）
scripts/                    # 工具脚本
├── install-hooks.sh        # Git Hooks 安装
└── seed_data.py            # 种子数据
tests/                      # 测试
```

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.11+, FastAPI |
| 存储 | SQLite（结构化图谱） |
| LLM | Anthropic SDK（支持兼容 API） |
| 协议 | MCP (Model Context Protocol) |
| 前端 | Jinja2 + D3.js |

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 代码检查
ruff check src/
```

## License

Apache License 2.0
