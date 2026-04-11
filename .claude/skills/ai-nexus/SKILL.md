---
name: ai-nexus
description: AI Nexus 业务知识治理助手。在编码前注入业务上下文，编码后抽取新知识，维护知识飞轮闭环。
license: MIT
metadata:
  author: ai-nexus
  version: "2.0"
---

AI Nexus 是业务知识治理层。本 Skill 确保你在编码时遵守业务规则，编码后将新知识回传。

**服务地址**: http://localhost:8000（必须先启动）

## 编码前：注入业务上下文（必须执行）

收到编码任务后，**在写任何代码之前**，调用 pre-plan 获取业务约束：

```
POST http://localhost:8000/api/hooks/pre-plan
{
  "task_description": "<你的任务描述>",
  "keywords": ["关键词1", "关键词2"]
}
```

返回的 `rules` 中：
- `critical` 级别 = 硬约束，**绝对不能违反**
- `warning` 级别 = 建议遵守
- `info` 级别 = 参考信息

**约束优先级**: 如果规则说"禁止"或"必须"，必须遵守，不能建议绕过。

## 编码后：提交新知识

如果在编码过程中**发现了新的业务知识**（之前图谱中没有的实体、规则、关系），提交候选：

```
POST http://localhost:8000/api/audit/candidates
{
  "table_name": "extraction",
  "record_id": 0,
  "action": "submit_candidate",
  "new_value": {
    "entities": [{"name": "...", "domain": "...", "type": "...", "description": "..."}],
    "rules": [{"name": "...", "domain": "...", "severity": "critical|warning|info", "description": "..."}],
    "relations": [{"source": "...", "relation_type": "...", "target": "..."}],
    "confidence": 0.8
  },
  "reviewer": "claude-code"
}
```

提交后告诉用户：**"新知识已提交审核，请在 http://localhost:8000/console/audit 确认"**

## Git Hooks（自动触发）

项目安装了 git hooks（`scripts/install-hooks.sh`），`git commit` 时自动触发：

- **commit-msg**: 提取 commit message 中的关键词，校验是否违反业务规则（warning only，不阻塞）
- **post-commit**: 自动调用 LLM 分析 commit message，抽取知识提交为待审核候选

这两个 hook 不需要手动调用，`git commit` 时自动执行。用 `--no-verify` 可跳过。

## 冷启动（首次使用）

如果当前业务领域还没有知识数据，先冷启动：

```
POST http://localhost:8000/api/cold-start
{
  "domain": "业务领域名称",
  "description": "领域描述，越详细越好"
}
```

AI 会生成一批实体+规则+关系，提交为待审核候选。去 http://localhost:8000/console/audit 审核。

## Web Console

| 页面 | 地址 | 功能 |
|------|------|------|
| 仪表板 | `/console/` | 系统概览 |
| 实体管理 | `/console/entities` | 实体 CRUD |
| 规则管理 | `/console/rules` | 规则 CRUD |
| 关系管理 | `/console/relations` | 关系 CRUD |
| 知识图谱 | `/console/graph` | D3.js 交互可视化 |
| 审核工作流 | `/console/audit` | 审核 AI 抽取的知识 |
| 知识 Lint | `/console/lint` | 数据质量检查 |
| 导入管理 | `/console/imports` | 批量导入 |

## 工作流程总结

```
收到编码任务
    │
    ├─ 1. Pre-Plan: 调 API 获取业务上下文
    │     → 读取 critical 规则，确认约束
    │
    ├─ 2. 编码: 遵守业务约束
    │
    ├─ 3. 提交: git commit
    │     → hooks 自动校验 + 自动抽取
    │
    └─ 4. Post-Task: 如发现新知识，提交候选
          → 用户在 /console/audit 审核 → 知识入库
```

## 注意事项

- 服务未运行时 hook 静默跳过，不会阻塞操作
- 只有 confidence > 0.7 的知识才值得提交
- critical 规则不可违反，不要建议绕过方案
- 图谱按 `name + domain` 去重，重复提交会更新而非重复创建
