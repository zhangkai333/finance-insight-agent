# AI 应用 / Agent 岗位 JD 能力摘要

> 更新日期：2026-10-07
> 用途：为 FinanceInsight Agent 反向设计项目能力，不代表对任何单一岗位的承诺。
> 参考依据：用户直接提供的 Agent 应用开发 JD；用户明确不再要求查询 BOSS 直聘。以下是技术要求与项目映射，不是市场调查结论。

## 目标岗位画像

面向企业级 AI 应用开发、Agent 应用开发、大模型应用工程师、RAG 应用工程师等岗位，重点不是训练模型，而是把 LLM 能力接入真实业务并稳定交付。

## 高频能力

### 1. 应用开发基础
- Python；Pandas / NumPy 等数据处理
- FastAPI / Flask 等 Web 后端
- SQL 与 MySQL / PostgreSQL
- Git、Linux、Docker；了解 CI/CD

### 2. LLM 应用能力
- OpenAI-compatible API 调用与封装
- Prompt Engineering / Context Engineering
- Structured Output
- Function Calling / Tool Use
- Agent 规划、状态管理、工作流编排

### 3. RAG 全链路
- 文档解析、清洗、切片、元数据管理
- Embedding、向量数据库、检索与重排
- 引用溯源、召回/生成质量评测

### 4. 工程化能力
- 异步任务、缓存、会话管理
- Retry、Fallback、超时与幂等
- 日志、Trace、回放、监控和成本/延迟分析
- Agent Evaluation 与反馈闭环
- MCP / 可复用工具或能力组件
- LangChain / LangGraph、BM25 / Rerank、Async / Concurrency、数据质量校验

## 项目映射

| JD 能力 | FinanceInsight Agent 中的真实用途 |
|---|---|
| Python / Pandas | 财报清洗、指标计算、异常检测、图表生成 |
| SQL / MySQL | 结构化财务事实查询 |
| LLM API | 问题理解、意图识别、任务规划、答案生成 |
| Structured Output | 将自然语言问题解析为可验证的查询计划 |
| Tool Calling | 让模型调用 SQL、RAG、分析、图表工具 |
| RAG / Embedding / Vector DB | 检索年报原文和经营原因 |
| LangGraph | 编排查询、计算、检索、校验和汇总节点 |
| FastAPI | 对外提供问数和任务执行 API |
| Redis / 异步 | 会话、缓存、长任务状态 |
| Docker | Compose 配置 API、MySQL 和 Redis；当前环境未实测 runtime |
| MCP | 将财务查询或报告能力暴露为标准工具 |
| Eval | 用赛题问题评测 SQL、检索和最终回答质量 |
| Logging / Trace | 记录每次路由、工具调用、耗时、错误和结果 |

## 设计结论

本项目应优先证明“业务闭环 + 工具可靠性 + 可解释性”，而不是堆叠框架。第一条主链路建议是：

用户问题 → 结构化问题解析 → SQL 查询 → Python 格式化结果 → 带来源的回答

随后再加入 RAG、图表和 LangGraph 多步骤编排。

当前已运行的本地演示是 Python/FastAPI、Pydantic、LangGraph、参数化 SQL、Python 计算、SQLite FTS5 RAG、词法重排、Trace 和定向 Eval。OpenAI-compatible/DeepSeek、Chroma/BGE-M3/jieba BM25、MySQL/Redis、MCP 与 Docker 有代码或配置入口，但本轮没有完成依赖/服务联调。面试中区分 workflow tool calling 与模型原生 function calling，不能把前者包装成后者。
