# 采集服务 + 数据契约 — 设计 Spec

- 日期:2026-07-04
- 状态:已批准(brainstorming 阶段),待转实现计划
- 范围:本 spec 只覆盖**子项目一**「隔离启动器 + 收尾摄取 + 磁盘数据契约」。macOS 展示 app 是**子项目二**,单独走一轮设计——但本契约会为它设计好。

---

## 1. 背景与动机

现状:`claude-context-lens` 是一套 Python + shell 工具链,分析 Claude Code 通过 OTel raw body dump 记录下来的 request/response JSON(见 `README.md`)。当前用法是手动跑脚本、输出 markdown。

目标是把它产品化成两段式系统:

```
后台采集(拿遥测→落盘)  ──契约──>  磁盘结构化存储  ──契约──>  原生 macOS 应用(解析+友好展示)
```

本 spec 设计前两段与中间契约;app 之后单独设计。

## 2. 目标 / 非目标

**核心目的:研究 / 学习 prompt 构造**——透明化 Claude Code 每一轮到底把什么塞进了 context window(system prompt、注入上下文、工具定义),以及**轮与轮之间怎么变**。

**目标:**
- 可靠、完整、不截断地捕获一次研究会话的全部 wire 级 request/response。
- 把原始 dump 归一成一份**磁盘契约**:两层结构(回合 → 请求),原始数据 + 派生拆解并存。
- 契约的 schema 作为单一真相源,供将来 Swift 端照抄。

**非目标(明确不做,各自另说):**
- macOS app(子项目二)。
- 常驻 daemon、SQLite、跨 session 搜索、成本分析、分享/导出。
- 多用户、云端、鉴权。

## 3. 锁定的约束(brainstorming 决策)

1. **绝不污染日常 claude 使用**——普通 `claude` 命令与日常会话一字不变、不被采集。
2. **纯本地、单用户的个人研究工具**——不上云、不联网、不做多用户/鉴权。
3. **采集方式 = 专用隔离启动器**:OTel 环境变量只作用于启动器拉起的子进程。这是「不污染日常」+「要完整 raw body」两个约束下唯一干净的解法(Claude Code 自带的 `~/.claude` transcript 不含 wire 级原始请求体)。
4. **存储形式 = 原始 body + 每轮派生 JSON**(文件树,透明可 grep)。原始 = 真相源;派生 = 缓存,可从原始重新生成。
5. **结构 = 两层:session → 回合(turn) → 请求(request)**。一个用户回合内,agent 的工具循环可能产生多次 API 请求,都归到该回合下。
6. **服务架构 = 启动器收尾摄取,无常驻进程**。采集由 OTel 后台实时进行;摄取在会话退出时跑一次。

## 4. 总体架构与数据流

```
你运行:  claude-lens run  [任意 claude 参数…]
            │  ① 隔离子进程里设 OTel 环境变量,透传参数给真实 claude
            ▼
        claude 正常跑(日常 claude 环境不变)
            │  ② Claude Code 后台实时把每次 wire 请求/响应写进本次会话的 raw/ 目录
            ▼
        会话退出(/exit 或 Ctrl-D)
            │  ③ 启动器收尾:对本次 raw/ 跑一遍摄取
            ▼
        摄取:配对 req↔resp → 排序 → 切回合 → 生成派生 JSON → 写 session.json
            ▼
        契约存储(磁盘,app 之后来读)
```

采集在后台实时发生(OTel),只有摄取在退出时跑一次;全程不碰默认 `claude`。

启动器透传所有 `claude` 参数(沿用 `run-claude-otel.sh` 里 `claude "$@"` 的做法)。设置的环境变量与现有脚本一致:`CLAUDE_CODE_ENABLE_TELEMETRY=1`、`OTEL_LOG_USER_PROMPTS=1`、`OTEL_LOG_TOOL_DETAILS=1`、`OTEL_LOG_TOOL_CONTENT=1`、`OTEL_LOG_RAW_API_BODIES=file:<session>/raw`、`OTEL_LOGS_EXPORTER=console`、`OTEL_METRICS_EXPORTER=none`、`OTEL_TRACES_EXPORTER=none`。

## 5. 数据契约(磁盘存储格式)—— 核心

默认存储根:`~/.claude-context-lens/sessions/`(在 repo 外,不进 git;可配置)。

```
<session-id>/                         # session-id = 启动时间戳,如 20260704-210526
  session.json                        # app 的唯一入口:会话元信息 + 回合/请求索引
  raw/                                # 真相源:OTel 原始 dump,逐字节原样,不改名不截断
    <uuid>.request.json
    req_<id>.response.json
    …
  derived/                            # 派生缓存:可从 raw 重新生成
    req-000.breakdown.json            # 每次请求的结构化拆解
    req-001.breakdown.json
    …
```

### 5.1 `session.json`(app 入口)

```jsonc
{
  "session_id": "20260704-210526",
  "captured_at": "2026-07-04T21:05:26Z",     // ISO 8601;由启动器在启动时刻写入
  "launcher_argv": ["claude", "..."],        // 启动器实际透传的参数
  "model": "claude-opus-4-8",
  "counts": { "turns": 3, "requests": 8, "responses": 8, "sidechannel": 2 },
  "turns": [
    {
      "index": 0,
      "user_message_preview": "你觉得还有哪些地方需要改进…",
      "requests": [
        {
          "index": 0,
          "raw_request":  "raw/42c8….request.json",
          "raw_response": "raw/req_011C….response.json",  // 可为 null(响应缺失/损坏)
          "breakdown":    "derived/req-000.breakdown.json",
          "previous_message_id": null,
          "order_confidence": "high:start",   // 复用现有 confidence 分级
          "is_sidechannel": false,            // 真实对话回合里恒为 false
          "usage":  { "input_tokens": 10570, "cache_read_input_tokens": 15298, "output_tokens": 4 },  // 可为 null
          "totals": { "system_chars": 7068, "message_chars": 33607, "tool_chars": 39053 }
        }
      ]
    }
  ],
  "sidechannel": [ /* 旁路请求(见下)的 meta,形状同 turns[].requests[],不进 turns */ ],
  "ambiguities": [   // 排序/配对存疑之处——显式暴露,不静默吞掉;统一形状 { kind, file, detail }
    { "kind": "order",            "file": "42c8….request.json",  "detail": "medium:null-prev" },
    { "kind": "corrupt-request",  "file": "…….request.json",     "detail": null },
    { "kind": "corrupt-response", "file": "…….response.json",    "detail": null },
    { "kind": "schema",           "file": null,                  "detail": "turn 0 request missing usage" }
  ]
}
```

所有路径为相对 `<session-id>/` 的相对路径,便于整个会话目录迁移。

注:请求项里的 `usage` / `totals` 是**摘要**(供 app 列表直接展示),完整明细在对应的 `breakdown.json`(见 5.2)。`totals.tool_chars` 是「工具描述 + schema」字符数的合计;`breakdown.json` 里拆成 `tool_description_chars` 与 `tool_schema_chars` 两项。

**旁路请求(`sidechannel[]`)**:Claude Code 会在后台发一些非对话请求(如「建议下一句」自动补全,注入 `[SUGGESTION MODE …]` 标记的用户消息)。它们与真实回合**同模型**,只能靠注入文本识别。这类请求**不进 `turns[]`**(否则会伪装成用户回合、甚至挤掉真实回合),而是单独收进 `sidechannel[]` 并标 `is_sidechannel: true`,数据不丢、由 app 决定是否展示。识别标记见 `turns.SIDECHANNEL_MARKERS`。

**ambiguities `kind` 取值**:`order`(排序/配对存疑,`detail` = order_confidence)/ `corrupt-request` / `corrupt-response`(`detail` = null)/ `schema`(`file` = null,`detail` = 校验问题描述)。`file` 为相对 `raw/` 的文件名或 null。

### 5.2 `derived/req-NNN.breakdown.json`(单次请求拆解)

由现有 `extract_context_window.py` 的产物演进为**一份 JSON**(而非一堆 `.md`),字段:

- `request_config`:model / max_tokens / stream / thinking / betas / context_management / output_config / metadata / diagnostics。
- `system[]`:每个 system 块的 type / text / cache_control / 字符数。
- `messages[]`:每条消息的每个 content block —— role / type / 解码后正文;`tool_use` 带 id、name;`tool_result` 带 tool_use_id、is_error(ANSI 已剥离);`thinking`/`redacted_thinking` 带 `available: false`、`text: ""`、`chars: 0`(见下)。
- `tools[]`:每个工具的 name / description / input_schema。
- `response`:响应内容块(同上,thinking 块带 `available: false`)。
- `usage`:响应的 token 账单原样保留(响应缺失时为 null)。
- `totals`:system / message / tool 描述 / tool schema 的字符数汇总。

**硬约束:thinking 正文不可采集。** Claude Code 的遥测层在写 `OTEL_LOG_RAW_API_BODIES` 前**无条件**把 thinking 抹成 `<REDACTED>`(源码 `uql()`,请求历史侧与响应侧都抹;无任何 env 开关保留)。故 breakdown 里 `thinking`/`redacted_thinking` 块一律标 `available: false`、正文置空、`chars: 0`(不把残留的 base64 signature 计入字符数)。app 应据此渲染「此处思考过、内容不可得」的占位。想拿到 thinking 正文只能改用「claude↔API 之间架网络代理」的另一套采集架构(不在本方案内)。

### 5.3 两个由现有代码支撑的机制

- **req↔resp 配对 & 排序**:靠 `request.diagnostics.previous_message_id → 上一个 response.id` 重建链条(来自 `analyze_session_requests.py` 的 `previous_message_id` / `confidence` 逻辑),带 confidence 分级;存疑进 `ambiguities`。某请求「自己的」响应由**下一条请求的 `previous_message_id`** 反推(现有 `add_response_to_next_links`)。
- **回合切分**:沿链条走,新回合 = 新增了「非 tool_result 的真实用户消息」;工具循环里的多次请求归到当前回合。比对用 `analyze_session_diffs.py` 的 `semantic_digest` / `normalize_message_for_compare`(忽略 `cache_control`)。

## 6. 组件与代码结构

复用现有脚本,收进一个 Python 包 + 一个 CLI:

```
claude_lens/
  cli.py            # `claude-lens run …` / `claude-lens ingest <raw-dir>`
  launcher.py       # §4①②:隔离子进程设 OTel 环境、透传参数、跑 claude、退出触发③
  ingest.py         # 摄取编排:配对→排序→切回合→写 session.json
  breakdown.py      # 由 extract_context_window.py 演进:raw body → breakdown.json
  linking.py        # 由 analyze_session_requests.py 演进:previous_message_id 链 + confidence
  turns.py          # 由 analyze_session_diffs.py 演进:回合切分 + semantic_digest
  contract.py       # session.json / 目录布局的 schema 与读写(单一真相源,供 Swift 端照抄)
```

- 语言:**Python**,直接复用已有且测试过的逻辑。
- `claude-lens` 做成可执行入口。
- 现有 4 个脚本保留为薄封装或迁移进包。

## 7. 错误处理与边界

- **会话中途崩溃 / 强杀**:收尾摄取可能拿到半份 dump → 摄取容错:能配对多少配多少,未配对请求照存并标 `order_confidence: low`,进 `ambiguities`,不整体失败。
- **半写 / 损坏文件**:只处理能完整 `json.load` 的文件;损坏的记进 `ambiguities`,跳过不崩。
- **字符串 content 消息**:已在 `extract_context_window.py` 修复(把纯字符串 content 归一为单个 text 块),摄取直接受益。
- **空会话 / 无请求**:生成合法的空 `session.json`,不报错。
- **补救通道**:`claude-lens ingest <raw-dir>` 可对任意历史 raw 目录手动重跑摄取(派生可再生)。

## 8. 测试与验收

- **TDD**,fixture 用真实采集的 dump(机器上 `~/claude-otel/` 那几份,含工具循环、字符串 content、多回合)。
- **黄金测试**:给定 raw 目录 → 摄取 → 断言 `session.json` 的回合数 / 请求数 / 配对 / confidence 与预期一致。
- **契约 schema 校验**:`session.json` 与 `breakdown.json` 可被 `contract.py` 的 schema 校验通过。
- **验收标准**:`claude-lens run -p "…"` 跑完后,`~/.claude-context-lens/sessions/<id>/` 出现结构完整、可被 schema 校验、回合↔请求↔raw 三者对得上的契约存储。

## 9. 后续(不在本 spec)

- 子项目二:macOS 展示 app,照本契约实现 Swift `Codable`,提供回合→请求两层浏览 + 相邻轮 diff 视图。
- 可能的索引层(SQLite),仅当出现跨 session 搜索/聚合需求时,作为 JSON 之上的派生缓存加入(JSON 仍为真相源)。
