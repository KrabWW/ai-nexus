# CLAUDE.md — AI Nexus 项目指南

## 项目定位

AI Nexus 是业务知识治理层，不是通用记忆系统。核心三件事：
1. 业务知识图谱（实体+关系+规则的 CRUD）
2. 开发流程 Hook（pre_plan 注入 + pre_commit 校验）
3. 知识审核工作流（AI 抽取 + 人工审核）

## 技术约束

- 后端：Python 3.11+, FastAPI
- 存储：SQLite（结构化）+ Qdrant（向量）
- 协议：MCP (Model Context Protocol)
- 不自建向量数据库层，不做通用记忆管理，不做文档库

## 代码规范

- 遵循 PEP 8
- 所有 public 函数需要 type hints
- 测试框架：pytest
- 提交前运行 `pytest` 和 `ruff check`

## 数据库

4 张核心表：entities, relations, rules, knowledge_audit_log
详见 docs/02-数据库设计.md

## MCP 工具

5 个核心工具：search_entities, search_rules, get_business_context, validate_against_rules, submit_knowledge_candidate
详见 docs/04-MCP-Server设计.md

## 当前阶段

Phase 0 — 基础设施接入（MCP Server 框架 + Qdrant + SQLite 初始化）
