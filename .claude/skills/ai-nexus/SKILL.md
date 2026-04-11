---
name: ai-nexus
description: AI Nexus 业务知识治理助手。三个触发点：编码前注入业务上下文、提交前校验规则、编码后抽取新知识，维护知识飞轮闭环。
license: MIT
metadata:
  author: ai-nexus
  version: "2.0"
---

AI Nexus 是业务知识治理层。本 Skill 定义三个触发点，确保编码遵守业务规则，并将新知识回传。

**前置条件**: AI Nexus 服务运行在 http://localhost:8000

## 触发点 1：编码前 — 注入业务上下文（必须执行）

**触发时机**：收到编码任务，写任何代码之前。

提取任务中的关键词（中文业务术语 + 英文实体名），调用 pre-plan：

```
POST http://localhost:8000/api/hooks/pre-plan
{
  "task_description": "<任务描述>",
  "keywords": ["关键词1", "关键词2"]
}
```

返回 `entities`（相关实体）和 `rules`（相关规则）。重点关注 `rules`：

| severity | 含义 | 处理方式 |
|----------|------|----------|
| `critical` | 硬约束 | **绝对不能违反**，不能建议绕过 |
| `warning` | 建议 | 尽量遵守，告知用户风险 |
| `info` | 参考 | 了解即可 |

**如果规则包含"禁止"或"必须"，必须遵守。**

## 触发点 2：提交前 — 校验业务规则

**触发时机**：准备提交代码时（git commit 前）。

用变更描述和涉及的实体名调用 pre-commit：

```
POST http://localhost:8000/api/hooks/pre-commit
{
  "change_description": "<变更描述>",
  "affected_entities": ["实体1", "实体2"]
}
```

返回 `errors`（critical 违规）、`warnings`（warning 提示）、`passed`（是否通过）。

- `passed: false` → 存在 critical 违规，需要修正或向用户确认
- `passed: true` → 可以提交

> 注意：Git commit-msg hook 也会在 `git commit` 时自动触发此校验（warning only），这里做的是提前检查。

## 触发点 3：编码后 — 提交新知识

**触发时机**：完成编码任务后，如果在过程中发现了新的业务知识。

将新知识提交为审核候选：

```
POST http://localhost:8000/api/audit/candidates
{
  "table_name": "extraction",
  "record_id": 0,
  "action": "submit_candidate",
  "new_value": {
    "entities": [
      {"name": "实体名", "domain": "业务领域", "type": "类型", "description": "描述"}
    ],
    "rules": [
      {"name": "规则名", "domain": "业务领域", "severity": "critical", "description": "规则描述"}
    ],
    "relations": [
      {"source": "源实体", "relation_type": "关系类型", "target": "目标实体"}
    ],
    "confidence": 0.8
  },
  "reviewer": "claude-code"
}
```

提交后告诉用户：**"新知识已提交审核，请在 http://localhost:8000/console/audit 确认"**

> 只有 confidence > 0.7 的知识才值得提交。图谱按 `name + domain` 去重。

## Git Hooks（自动触发，无需手动调用）

项目安装了 git hooks（安装方式：`bash scripts/install-hooks.sh`）：

- **commit-msg**：`git commit` 时自动校验 commit message 是否违反规则（warning only）
- **post-commit**：`git commit` 后自动调用 LLM 分析，抽取知识提交为待审核候选

用 `git commit --no-verify` 可跳过。

## 冷启动（首次使用）

新业务领域没有知识时，先冷启动建立初始框架：

```
POST http://localhost:8000/api/cold-start
{
  "domain": "业务领域名称",
  "description": "详细描述该领域的核心功能和规则"
}
```

去 http://localhost:8000/console/audit 审核生成的候选项。

## 完整工作流

```
收到编码任务
    │
    ▼ 触发点 1: Pre-Plan
    │  调 API 获取业务上下文
    │  读取 critical 规则 → 确认约束
    │
    ▼ 编码
    │  遵守业务约束写代码
    │
    ▼ 触发点 2: Pre-Commit
    │  校验变更是否违反规则
    │  passed=true → 可以提交
    │  passed=false → 修正或确认
    │
    ▼ git commit
    │  hooks 自动校验 + 自动抽取知识
    │
    ▼ 触发点 3: Post-Task
    │  发现新知识？→ 提交候选
    │  用户在 /console/audit 审核 → 知识入库
    │
    ▼ 知识飞轮：更多知识 → 更好的校验 → 更好的代码
```
