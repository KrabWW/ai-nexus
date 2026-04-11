---
name: knowledge-hooks
description: Inject business context before starting work and submit new knowledge after completion. Use at the start and end of every coding task to maintain the knowledge flywheel.
license: MIT
metadata:
  author: ai-nexus
  version: "1.0"
---

Inject business knowledge context before work and capture new knowledge after completion.

**Input**: A task description (what you're about to work on or just completed).

**When to use**:
- At the START of every coding task (pre-plan phase)
- At the END of every coding task (post-task phase)
- When you discover new business rules during work

## Pre-Plan (Before Starting Work)

**Step 1**: Extract keywords from the task description (Chinese business terms + English entity names).

**Step 2**: Call MCP tool `get_business_context`:
```
get_business_context(task_description="<task>", keywords=["keyword1", "keyword2"])
```

**Step 3**: Review the returned context:
- **Entities**: Understand which business objects are involved
- **Rules**: Pay special attention to `critical` severity rules — these are hard constraints
- If any rule says "禁止" or "必须", do NOT violate it

**Step 4**: Acknowledge the constraints and proceed with implementation.

## Post-Task (After Completing Work)

**Step 1**: If you discovered or inferred new business knowledge during work, submit each item:

For entities:
```
submit_knowledge_candidate(type="entity", data={"name": "...", "domain": "...", "type": "...", "description": "..."}, source="claude-code", confidence=0.8)
```

For rules:
```
submit_knowledge_candidate(type="rule", data={"name": "...", "domain": "...", "severity": "critical|warning|info", "description": "..."}, source="claude-code", confidence=0.8)
```

**Step 2**: Tell the user: "新知识已提交审核，请在 http://localhost:8000/console/audit 确认"

## Git Hooks (Automatic)

The project has pre-configured git hooks:
- `commit-msg`: Validates commit against business rules (warning only)
- `post-commit`: Auto-extracts knowledge from commit message via LLM

These fire automatically on `git commit`. Use `--no-verify` to skip.

## Examples

### Pre-Plan Example
Task: "修改订单支付超时逻辑"
→ Call: `get_business_context("修改订单支付超时逻辑", keywords=["订单", "支付", "超时"])`
→ Response: 8 entities + 8 rules including "订单状态单向流转" (critical)
→ Note: "禁止删除已支付订单" — must not violate this rule

### Post-Task Example
Completed: "新增商品评分功能"
→ Discovered: 用户只能对同一商品评分一次
→ Call: `submit_knowledge_candidate(type="rule", data={"name": "商品评分唯一性", "domain": "商品管理", "severity": "critical", "description": "每个用户只能对同一商品评分一次"}, source="claude-code", confidence=0.9)`

## Important Notes

- Always call pre-plan BEFORE writing any code
- Critical rules are non-negotiable constraints — never suggest code that violates them
- Only submit knowledge you're confident about (confidence > 0.7)
- The knowledge flywheel: more commits → more knowledge → better validation → better code
