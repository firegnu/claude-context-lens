# 会话交接 (HANDOFF)

> 日期:2026-07-04 · 分支:main(已与 origin 同步)· 状态:设计+计划完成,**实现未开始**

## 快速恢复(下次 session 开场)

读这三份即可完整恢复上下文:
1. 本文件 `HANDOFF.md`(当前进度 + 下一步)
2. `docs/superpowers/specs/2026-07-04-capture-service-and-data-contract-design.md`(设计 spec)
3. `docs/superpowers/plans/2026-07-04-capture-service-and-data-contract.md`(8 个 TDD Task 的实现计划)

一句话开场:「继续 claude-context-lens 的 capture 服务开发,按 `docs/superpowers/plans/2026-07-04-capture-service-and-data-contract.md` 从 Task 1 开始,执行方式选 X」。

## 1. 会话摘要

把 `claude-context-lens`(分析 Claude Code OTel raw body dump 的脚本工具链)产品化:先修好上下文提取器的两个 bug,再通过 brainstorming → spec → plan 完整设计了**子项目一「隔离启动器 + 收尾摄取 + 磁盘数据契约」**(命令名 `claude-lens`)。实现代码尚未动工。

## 2. 完成的工作

- **修复** `scripts/extract_context_window.py` 两处(含测试):
  - `tool_result` 块渲染:剥 ANSI + 输出元信息(`a215af6`)
  - 字符串 message content 崩溃:归一为单个 text 块(`d46e123`)
- **采集**了一份最新真实遥测:`~/claude-otel/bodies-20260704-210526/`(1 req + 1 resp,含字符串 content 消息);并生成拆解产物 `~/claude-otel/breakdown-20260704-210526/`。
- **写并提交**了设计 spec(`9e16b63`)和实现计划(`e07b212`),均已 push。
- 所有 4 个 commit 已推送到 `origin/main`,工作区干净。

## 3. 待完成的工作

- **执行实现计划**:新建 `claude_lens/` 包(contract/breakdown/linking/turns/ingest/launcher/cli)+ 测试,共 8 个 Task。**一行都还没写。**
- **待决策**:执行方式 —— **1. Subagent-Driven(推荐)** 每 Task 派新 subagent + 审查;**2. Inline** 当前会话批量执行带检查点。
- **子项目二**:原生 macOS 展示 app,照契约实现 Swift `Codable`,做「回合→请求」两层浏览 + 相邻轮 diff —— 需另起一轮 brainstorming/spec/plan。

## 4. 关键决策(及理由)

- **目的 = 研究/学习 prompt 构造**(每轮 + 演进 diff 是核心);token 成本、缓存优化、分享导出降级,MVP 不做。
- **绝不污染日常 claude** → 采集只能用**专用隔离启动器**(OTel 环境变量只作用于子进程);普通 `claude` 一字不变。这是「不污染 + 要完整 raw body」下唯一干净解。
- **存储 = 原始 body + 每轮派生 JSON 文件树**(非 SQLite):透明可 grep、raw=真相源、derived=可再生缓存。SQLite 的跨库搜索优势对应已砍掉的目的,YAGNI。
- **结构 = 两层:session → 回合(turn) → 请求(request)**。一个用户回合内工具循环的多次请求归到该回合。
- **服务 = 启动器收尾摄取,无常驻 daemon**:采集本就是 OTel 后台实时写,只把解析放到退出时跑一次;最简、故障面最小,日后要实时再加薄 daemon 复用同一摄取核心。
- **测试用 `python3 -m unittest`(不是 pytest)**——项目约定,无第三方依赖。
- **PII**:raw body 含邮箱/device_id/account_uuid/路径;本地存储 `~/.claude-context-lens/` 可以,但**绝不提交真实采集数据或据其派生的 fixture**(单测 fixture 用合成数据)。

## 5. 重要文件

- `docs/superpowers/specs/2026-07-04-capture-service-and-data-contract-design.md` — 设计 spec
- `docs/superpowers/plans/2026-07-04-capture-service-and-data-contract.md` — 实现计划(8 Task,含完整代码)
- `scripts/extract_context_window.py` + `tests/test_extract_context_window.py` — 已修复的提取器(逻辑将被计划里的 `claude_lens/breakdown.py` 复用)
- `scripts/analyze_session_requests.py`(req↔resp 配对/排序逻辑来源)、`scripts/analyze_session_diffs.py`(回合切分/semantic_digest 来源)
- `~/claude-otel/bodies-20260704-210526/` — 最新真实采集(计划 Task 8 smoke test 可用 `~/claude-otel/bodies-20260504-111512` 那份多回合数据)
- 待创建:`claude_lens/`(包)、`pyproject.toml`(仓库目前无)

## 6. 下一步建议(按优先级)

1. **定执行方式(1 或 2),开跑 Task 1**(`claude_lens/contract.py` + 测试,TDD)。
2. **按计划 Task 1→8 顺序 TDD 实现**,每 Task 一个 commit;Task 8 用真实 dump 做 smoke test。
3. **实现验收后**,再开子项目二(macOS app)的 brainstorming。

## ⚠️ 未提交变更提醒

当前工作区**干净**,无未提交代码变更(本 `HANDOFF.md` 除外——如需持久化请提交)。所有既有 commit 已 push。
