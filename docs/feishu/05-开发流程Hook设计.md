# 05-开发流程Hook设计

> 来源：飞书知识库 | 最后编辑：2026-04-06

## 核心理念

把业务知识系统嵌进 AI 的开发循环里——不用刻意调用，关键时刻总会出现。

## 两个核心 Hook

### Hook 1：pre_plan — 业务上下文注入

**触发时机**：AI 开始规划任务时
**调用工具**：`get_business_context`

```
任务："实现医生排班模块"
    │
    ▼
get_business_context(task_description="实现医生排班模块")
    │
    ▼
返回：
  相关实体：[医生, 排班, 科室, ICU]
  相关规则：
    - ICU必须24小时值班 (error)
    - 排班周期为7天 (info)
    - 三级医院排班规则 (warning)
  关系网络：
    医生→属于→科室
    医生→排班→门诊
    ICU→需要→24小时值班
    │
    ▼
自动拼入 AI 的 prompt
```

**实现方式**：Claude Code 的 `hooks` 配置，在 `PreToolUse` 或自定义触发点执行。

### Hook 2：pre_commit — 规则校验

**触发时机**：AI 准备提交代码时
**调用工具**：`validate_against_rules`

```
AI 写了：
  EmergencyRoom open_time = "8:00"
    │
    ▼
validate_against_rules(
  change_description="设置急诊开放时间",
  affected_entities=["EmergencyRoom"],
  diff_summary="新增 open_time 字段赋值为 8:00"
)
    │
    ▼
返回：
  违反规则：急诊应24小时开放 (severity: error)
  建议：open_time = "0:00"  # 24小时开放
    │
    ▼
提示 AI 修正
```

**实现方式**：Claude Code hooks 的 `PreCommit` 阶段执行。

## Hook 配置示例

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python -m ai_nexus.hooks.pre_plan"
          }
        ]
      }
    ],
    "PreCommit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -m ai_nexus.hooks.pre_commit"
          }
        ]
      }
    ]
  }
}
```

## Hook 工作流

```
Claude Code 接到任务
       │
       ▼
  pre_plan Hook 触发
       │
       ├─ 从图谱检索相关业务上下文
       ├─ 注入到 AI 的 prompt
       │
       ▼
  AI 编写代码（带着业务上下文）
       │
       ▼
  pre_commit Hook 触发
       │
       ├─ 扫描代码变更
       ├─ 校验业务规则
       ├─ 违反则提示修正
       │
       ▼
  提交代码
       │
       ▼
  （可选）post_task 自动抽取新知识
```

## MVP 阶段不做的事

- 不做复杂 AI Supervisor 调度系统
- 不做跨模块冲突自动检测
- 不做实时任务进度监控面板
- 不做 post_task 知识自动更新（Phase 3 再做）
