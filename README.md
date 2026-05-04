# Claude Code Raw Body Analysis Toolkit

这个目录里有四个脚本，用来采集并分析 Claude Code 通过 OTel raw body dump 记录下来的 request/response JSON。

它们分别解决四个层级的问题：

```text
0. 启动 Claude Code 并采集 raw request/response body
1. 单个 request 的 context window 拆解
2. 一个 session 中多个 request 的逻辑排序
3. 一个 session 中相邻 request 的逐轮变化分析
```

推荐使用顺序：

```bash
scripts/run-claude-otel.sh

python3 scripts/analyze_session_requests.py \
  --session-dir "$HOME/claude-otel/bodies-YYYYMMDD-HHMMSS" \
  --out "$HOME/claude-otel/session_request_order-YYYYMMDD-HHMMSS"

python3 scripts/analyze_session_diffs.py \
  --session-dir "$HOME/claude-otel/bodies-YYYYMMDD-HHMMSS" \
  --order "$HOME/claude-otel/session_request_order-YYYYMMDD-HHMMSS/session_manifest.json" \
  --out "$HOME/claude-otel/session_diffs-YYYYMMDD-HHMMSS"

python3 scripts/extract_context_window.py \
  --request "$HOME/claude-otel/bodies-YYYYMMDD-HHMMSS/<some>.request.json" \
  --response "$HOME/claude-otel/bodies-YYYYMMDD-HHMMSS/<some>.response.json" \
  --out context_window_breakdown
```

## 0. `run-claude-otel.sh`

用途：带 OTel raw body dump 启动 Claude Code，把每次 API request/response 原始 body 写入文件。

命令：

```bash
scripts/run-claude-otel.sh
```

也可以把 Claude Code 参数原样透传进去：

```bash
scripts/run-claude-otel.sh --help
scripts/run-claude-otel.sh path/to/project
```

脚本会创建：

```text
$HOME/claude-otel/
├── run-YYYYMMDD-HHMMSS.log
└── bodies-YYYYMMDD-HHMMSS/
    ├── <uuid>.request.json
    ├── req_<id>.response.json
    └── ...
```

脚本设置的关键环境变量：

```bash
CLAUDE_CODE_ENABLE_TELEMETRY=1
OTEL_LOG_USER_PROMPTS=1
OTEL_LOG_TOOL_DETAILS=1
OTEL_LOG_TOOL_CONTENT=1
OTEL_LOG_RAW_API_BODIES="file:$BODIES_DIR"
OTEL_LOGS_EXPORTER=console
OTEL_METRICS_EXPORTER=none
OTEL_TRACES_EXPORTER=none
```

其中最重要的是：

```bash
OTEL_LOG_RAW_API_BODIES="file:$BODIES_DIR"
```

`file:` 模式会把 raw API body 写成完整 JSON 文件，适合后续分析 context window。

运行时脚本会打印：

```text
>>> Telemetry events log: /Users/<user>/claude-otel/run-YYYYMMDD-HHMMSS.log
>>> Raw bodies dir:       /Users/<user>/claude-otel/bodies-YYYYMMDD-HHMMSS
>>> Starting claude... (use /exit or Ctrl-D to quit)
```

退出 Claude Code 后，脚本会打印：

```text
>>> Done.
>>> Events log size:   ...
>>> Raw bodies count:  ... requests
>>> Bodies dir size:   ...
```

注意事项：

- `stdout` 保留给 Claude Code 的 TTY 交互，只把 `stderr` tee 到 log 文件。
- `run-*.log` 不一定有内容；真正稳定可用的分析输入是 `bodies-*/*.request.json` 和 `bodies-*/*.response.json`。
- raw body 文件名不能表示逻辑顺序，后续必须用 `analyze_session_requests.py` 恢复顺序。
- raw body 可能包含用户输入、项目路径、邮箱、metadata、工具结果等敏感信息，分享前需要脱敏。

采集完成后，先复制或记下脚本打印的 `Raw bodies dir`，例如：

```text
$HOME/claude-otel/bodies-20260504-111512
```

后续分析脚本都以这个目录作为 `--session-dir`。

## 1. `extract_context_window.py`

用途：分析单次 Claude Code API request/response，把这一次请求中的 context window 按结构拆出来。

命令：

```bash
python3 scripts/extract_context_window.py \
  --request path/to/file.request.json \
  --response path/to/file.response.json \
  --out path/to/context_window_breakdown
```

`--response` 是可选的。如果只想分析 request：

```bash
python3 scripts/extract_context_window.py \
  --request path/to/file.request.json \
  --out path/to/context_window_breakdown
```

输出结构：

```text
context_window_breakdown/
├── 00_request_config.json
├── 01_system/
│   ├── 00.md
│   ├── 01.md
│   └── ...
├── 02_messages/
│   ├── message_00_content_00.md
│   ├── message_00_content_01.md
│   └── ...
├── 03_tools/
│   ├── 00_Agent.json
│   ├── 01_Bash.json
│   └── ...
├── 03_tools_summary.json
├── 04_response/
│   └── content_00.md
└── manifest.json
```

各文件含义：

- `00_request_config.json`：模型、`max_tokens`、`thinking`、`betas`、`context_management` 等请求配置。它不是 prompt 文本，但会影响模型运行方式。
- `01_system/`：顶层 `system[]` 内容。这里通常是 Claude Code 的系统级规则、身份、运行时说明等。
- `02_messages/`：`messages[].content[]` 内容。这里既可能有真实用户输入，也可能有 Claude Code 注入的 `<system-reminder>`、skills 列表、MCP 指令、CLAUDE.md 等。
- `03_tools/`：本轮 request 中直接提供给模型的 tools schema。
- `03_tools_summary.json`：工具名称、description 长度、schema 长度摘要。
- `04_response/`：模型 response content。严格说它不是输入 context window，只是为了把这一轮交互闭环保存。
- `manifest.json`：总索引，记录每个拆分块的顺序、来源、字符数、文件路径和 preview。

适合探索的问题：

```text
这一轮 request 的 system prompt 到底有几段？
真实用户输入在 messages 的哪个 content block？
tools[] 里有哪些工具？
system/messages/tools 各自大概占多少字符？
response 的 stop_reason 和 usage 是什么？
```

常用查看命令：

```bash
jq '.totals, .sections[] | {order, kind, file, chars, preview}' \
  context_window_breakdown/manifest.json

jq '.request_config' context_window_breakdown/manifest.json

sed -n '1,120p' context_window_breakdown/01_system/02.md
```

## 2. `analyze_session_requests.py`

用途：分析一个 session 目录中所有 raw body 文件，恢复 request 的逻辑顺序，并尽量推断 request/response 的对应关系。

Claude Code raw body 文件名通常是 UUID 或 `req_xxx`，不能直接表示时间顺序。这个脚本不按文件名排序，也不主要依赖 mtime，而是使用：

```text
1. messages_count 递增
2. request.diagnostics.previous_message_id
3. response.id
4. mtime_ns 作为 tie-breaker
```

命令：

```bash
python3 scripts/analyze_session_requests.py \
  --session-dir path/to/bodies-YYYYMMDD-HHMMSS \
  --out path/to/session_request_order
```

如果不传 `--out`，默认输出到：

```text
<session-dir>/session_request_order
```

输出结构：

```text
session_request_order/
├── session_manifest.json
└── timeline.md
```

`session_manifest.json` 主要字段：

- `session_dir`：被分析的 raw bodies 目录。
- `counts.requests` / `counts.responses`：request/response 数量。
- `ordering_strategy`：排序策略说明。
- `ordered_requests`：排序后的 request 列表。
- `responses`：按 mtime 排列的 response 摘要。
- `ambiguities`：排序或链路中不确定的地方。

`ordered_requests[]` 中的重要字段：

- `index`：逻辑顺序号。
- `request_file`：request 文件名。
- `messages_count`：该 request 中 `messages` 数量。
- `previous_message_id`：request 内部记录的上一条 assistant message id。
- `previous_response_file`：由 `previous_message_id -> response.id` 找到的上一个 response 文件。
- `inferred_response_file`：通过下一轮 request 的 `previous_message_id` 反推出来的本轮 response。
- `confidence`：排序置信度。

置信度含义：

```text
high:start
  session 起点，previous_message_id 为 null。

high:linked
  previous_message_id 可以匹配到某个 response.id。

medium:null-prev
  previous_message_id 为 null，但不是第一个 request，可能是新用户输入、reset、分支或特殊请求。

low:missing-prev-response
  previous_message_id 存在，但找不到对应 response。
```

`timeline.md` 是人类可读的顺序表，适合先快速浏览。

适合探索的问题：

```text
这个 session 有多少轮 request？
request 的逻辑顺序是什么？
哪些 request 的 previous_message_id 链接清楚？
哪些 request 可能是 reset/分支/特殊请求？
每个 request 推断对应哪个 response？
```

常用查看命令：

```bash
sed -n '1,160p' body-request-202605041115/session_request_order/timeline.md

jq '.ordered_requests[] | {index, messages_count, confidence, request_file, previous_response_file, inferred_response_file}' \
  body-request-202605041115/session_request_order/session_manifest.json

jq '.ambiguities' \
  body-request-202605041115/session_request_order/session_manifest.json
```

## 3. `analyze_session_diffs.py`

用途：基于已经排序好的 request 列表，逐个比较相邻 request，观察 Claude Code harness 每一轮如何重组 context window。

这个脚本回答的问题是：

```text
request[N] 相比 request[N-1] 到底变了什么？
```

命令：

```bash
python3 scripts/analyze_session_diffs.py \
  --session-dir path/to/bodies-YYYYMMDD-HHMMSS \
  --order path/to/session_request_order/session_manifest.json \
  --out path/to/session_diffs
```

如果不传 `--out`，默认输出到：

```text
<session-dir>/session_diffs
```

输出结构：

```text
session_diffs/
├── session_diff_manifest.json
├── session_story.md
├── timeline_diff.md
├── events.jsonl
└── turns/
    ├── 0001.json
    ├── 0001.md
    ├── 0002.json
    ├── 0002.md
    └── ...
```

`session_story.md` 是推荐的主阅读入口。它把底层 JSON diff 转换成 agent loop 叙事：

- 这一轮发生了什么，例如工具循环推进、用户新消息、非纯追加。
- 当前 request 文件和本轮 response 摘要。
- system/tools/config 是否稳定。
- 本轮 context window 新增了哪些 message。
- 如果有 tool_use/tool_result，会直接显示工具名、输入预览和结果预览。

`events.jsonl` 是机器可分析事件流，每行一个事件，常见事件包括：

- `tool_use`
- `tool_result`
- `user_text`
- `assistant_text`
- `metadata_only_changed`
- `message_removed_or_rewritten`
- `system_changed`
- `tools_changed`

`turns/000N.md` 是单轮人类可读详情；`turns/000N.json` 是同一轮的结构化证据。

`timeline_diff.md` 是人类可读总览。每一行展示：

- turn 序号
- `meaning`：对这一轮变化的人话解释，例如工具循环推进、用户新消息、非纯追加
- `messages` 数量变化，例如 `15->17`
- common prefix 数量，按语义内容比较，忽略 `cache_control`
- 新增 message 数量
- 被改写或删除的 message 数量
- `meta`：只有 `cache_control` 等元数据变化的 message 数量
- system 是否变化
- tools 是否变化
- request 文件名

`turns/000N.json` 是单轮结构化 diff，适合深入分析。

每个 turn diff 的主要结构：

```json
{
  "index": 2,
  "request_file": "...request.json",
  "previous_request_file": "...request.json",
  "confidence": "high:linked",
  "response": {
    "file": "...response.json",
    "id": "msg_xxx",
    "stop_reason": "tool_use",
    "content_types": ["tool_use"],
    "usage": {}
  },
  "config": {
    "changed": false,
    "hash": "..."
  },
  "system": {
    "changed": false,
    "count": 4,
    "changed_indexes": []
  },
  "tools": {
    "count": 8,
    "changed": false,
    "added": [],
    "removed": [],
    "changed_names": []
  },
  "messages": {
    "previous_count": 1,
    "current_count": 3,
    "common_prefix_count": 1,
    "raw_common_prefix_count": 0,
    "append_only": true,
    "added_count": 2,
    "removed_or_rewritten_count": 0,
    "metadata_only_changed_indexes": [0],
    "reset_or_rewrite_suspected": false,
    "added": [],
    "removed_or_rewritten": []
  }
}
```

关键字段解释：

- `common_prefix_count`：当前 request 和上一轮 request 从头开始有多少 message 语义相同。比较时会忽略 `cache_control`，并把字符串 text 与 `[{type:"text"}]` 形式视为同一种文本消息。
- `raw_common_prefix_count`：按原始 JSON 完全一致比较时的 common prefix。
- `append_only`：是否只是单纯在上一轮 messages 后面追加。
- `metadata_only_changed_indexes`：语义相同但原始 JSON 不同的 message 下标，通常是 `cache_control` 变化。
- `added`：从第一个不同位置开始，当前 request 中新增/替换出来的 messages 摘要。
- `removed_or_rewritten`：上一轮中从第一个不同位置开始，被当前 request 替换掉的 messages 摘要。
- `reset_or_rewrite_suspected`：如果不是 append-only，就标记为 true。它不一定代表真正 compaction，也可能只是 tool_result 内容或 thinking 内容被重写。
- `system.changed`：顶层 `system[]` 是否变化。
- `tools.changed`：`tools[]` 是否变化。

message 摘要字段：

- `index`：message 在 `messages[]` 中的位置。
- `role`：`user` / `assistant` 等。
- `content_types`：content block 类型，例如 `text`、`thinking`、`tool_use`、`tool_result`。
- `text_chars`：文本字符数。
- `preview`：文本预览。
- `tool_use_ids`：assistant tool_use 的 id。
- `tool_result_ids`：user tool_result 对应的 tool_use_id。
- `hash`：该 message 的稳定 hash。

适合探索的问题：

```text
每一轮 messages 是 append，还是发生了改写？
哪一轮加入了真实用户输入？
哪一轮加入了 assistant tool_use？
哪一轮加入了 user tool_result？
system prompt 在 session 中是否变化？
tools schema 在 session 中是否变化？
Claude Code 是否在某些轮次注入了 suggestion mode 或其他特殊消息？
```

常用查看命令：

```bash
sed -n '1,220p' body-request-202605041115/session_diffs/session_story.md

sed -n '1,220p' body-request-202605041115/session_diffs/timeline_diff.md

sed -n '1,120p' body-request-202605041115/session_diffs/turns/0009.md

jq -r 'select(.event=="tool_use") | [.turn, .tool, .preview] | @tsv' \
  body-request-202605041115/session_diffs/events.jsonl

jq '.turn_diffs[] | {index, request_file, system_changed:.system.changed, tools_changed:.tools.changed, messages:.messages | {previous_count, current_count, common_prefix_count, added_count, removed_or_rewritten_count, reset_or_rewrite_suspected}}' \
  body-request-202605041115/session_diffs/session_diff_manifest.json

jq '.messages.added[] | {index, role, content_types, preview, tool_use_ids, tool_result_ids}' \
  body-request-202605041115/session_diffs/turns/0009.json
```

## 推荐探索流程

### A. 先采集 raw bodies

```bash
scripts/run-claude-otel.sh
```

在 Claude Code 中正常完成你的探索或开发任务，然后用 `/exit` 或 Ctrl-D 退出。

记录脚本输出中的 raw bodies 目录：

```text
>>> Raw bodies dir: /Users/<user>/claude-otel/bodies-YYYYMMDD-HHMMSS
```

下面的例子统一用这个变量表示：

```bash
SESSION_DIR="$HOME/claude-otel/bodies-YYYYMMDD-HHMMSS"
SESSION_TS="YYYYMMDD-HHMMSS"
```

### B. 恢复 session 顺序

```bash
python3 scripts/analyze_session_requests.py \
  --session-dir "$SESSION_DIR" \
  --out "$HOME/claude-otel/session_request_order-$SESSION_TS"
```

先看：

```bash
sed -n '1,160p' "$HOME/claude-otel/session_request_order-$SESSION_TS/timeline.md"
```

重点关注：

```text
confidence 是否大多为 high
是否有 duplicate_messages_count
是否有 medium:null-prev
```

### C. 再看逐轮变化

```bash
python3 scripts/analyze_session_diffs.py \
  --session-dir "$SESSION_DIR" \
  --order "$HOME/claude-otel/session_request_order-$SESSION_TS/session_manifest.json" \
  --out "$HOME/claude-otel/session_diffs-$SESSION_TS"
```

先看：

```bash
sed -n '1,220p' "$HOME/claude-otel/session_diffs-$SESSION_TS/timeline_diff.md"
```

重点关注：

```text
messages 是否持续增长
common_prefix_count 是否突然变小
system 是否变化
tools 是否变化
哪些 added message 是真实用户输入
哪些 added message 是 tool_use/tool_result
```

### D. 对感兴趣的一轮做单 request 拆解

从 `timeline.md` 或 `timeline_diff.md` 里挑一个 request 文件，然后运行：

```bash
python3 scripts/extract_context_window.py \
  --request "$SESSION_DIR/<request-file>" \
  --out context_window_breakdown
```

如果你知道对应 response，也可以加上：

```bash
--response "$SESSION_DIR/<response-file>"
```

然后打开：

```bash
context_window_breakdown/manifest.json
context_window_breakdown/01_system/
context_window_breakdown/02_messages/
context_window_breakdown/03_tools/
```

这样可以从 session 级别一路钻到单轮 request 的具体 context window 内容。

## 注意事项

1. 文件名不能表示 request 顺序。

Claude Code raw body 文件名通常是 UUID 或 `req_xxx`，不能按文件名排序。

2. 文件 mtime 不能作为唯一依据。

raw body exporter 可能异步落盘。同一个 session 中可能出现逻辑上较早的 request 文件 mtime 反而更晚。

3. `messages_count` 是强信号，但不是绝对真理。

普通线性 session 中它通常递增，但 reset、compaction、suggestion mode、分支请求都可能打破简单模式。

4. `previous_message_id -> response.id` 是最重要的链路信号。

它通常表示：

```text
某个 response 发生在当前 request 之前
```

相邻 request 的 response 可以通过下一轮 request 的 `previous_message_id` 反推。

5. `reset_or_rewrite_suspected` 只是结构提示。

它表示相邻 request 不是纯 append。原因可能是 tool_result 内容变化、thinking 内容变化、suggestion mode 注入、context rewrite、compaction 或其他 harness 行为，需要结合具体 `turns/000N.json` 查看。

## 运行测试

所有测试都使用 Python 标准库 `unittest`，不需要安装 pytest。

```bash
python3 -m unittest \
  tests.test_extract_context_window \
  tests.test_analyze_session_requests \
  tests.test_analyze_session_diffs
```
