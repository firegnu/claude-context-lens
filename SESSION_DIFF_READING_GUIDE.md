# 如何阅读 Session Request Diff

这个文档说明如何阅读 `analyze_session_diffs.py` 生成的文件，用来理解同一个 Claude Code session 中相邻 request 之间的变化。

核心心智模型：

```text
turns/0009.json = request[9] - request[8]
```

这里的 `request[9]` 和 `request[8]` 不是按文件名或 mtime 排序，而是按 `analyze_session_requests.py` 恢复出来的逻辑顺序排序。

## 输出目录

运行：

```bash
python3 scripts/analyze_session_diffs.py \
  --session-dir body-request-202605041115/bodies-20260504-111512 \
  --order body-request-202605041115/session_request_order/session_manifest.json \
  --out body-request-202605041115/session_diffs
```

会生成：

```text
body-request-202605041115/session_diffs/
├── session_diff_manifest.json
├── timeline_diff.md
└── turns/
    ├── 0001.json
    ├── 0002.json
    └── ...
```

## 第一步：先看总览

先打开：

```text
body-request-202605041115/session_diffs/timeline_diff.md
```

或者用命令：

```bash
sed -n '1,220p' body-request-202605041115/session_diffs/timeline_diff.md
```

`timeline_diff.md` 的每一行表示：

```text
当前 request 相比上一个 request 的变化
```

表格字段：

```text
turn        当前 request 的逻辑序号
messages    上一轮 messages 数 -> 当前 messages 数
prefix      两轮从头开始完全相同的 message 数
added       当前 request 从第一个不同点开始新增/替换出来的 message 数
rewritten   上一轮从第一个不同点开始被替换掉的 message 数
system      system[] 是否变化
tools       tools[] 是否变化
request     当前 request 文件
```

例子：

```text
| 9 | 15->17 | 14 | 3 | 1 | same | same | ...
```

含义：

```text
第 9 个 request 相比第 8 个 request：
上一轮有 15 条 messages
当前有 17 条 messages
前 14 条完全相同
从 message[14] 开始发生变化
当前新增/替换出了 3 条 message
上一轮尾部有 1 条 message 被替换
system 没变
tools 没变
```

## 第二步：打开某一轮的详细 JSON

如果你想看第 9 轮，打开：

```text
body-request-202605041115/session_diffs/turns/0009.json
```

或者：

```bash
jq '.' body-request-202605041115/session_diffs/turns/0009.json
```

每个 turn diff 的顶层结构大致是：

```json
{
  "index": 9,
  "request_file": "...",
  "previous_request_file": "...",
  "confidence": "high:linked",
  "response": {},
  "config": {},
  "system": {},
  "tools": {},
  "messages": {}
}
```

各字段含义：

```text
index
  当前 request 的逻辑序号。

request_file
  当前 request 文件。

previous_request_file
  上一个逻辑 request 文件。

confidence
  当前 request 在排序阶段的置信度。

response
  通过排序链路推断出的当前 request 对应 response 摘要。

config
  request 配置是否变化，例如 model、max_tokens、thinking、betas 等。

system
  顶层 system[] 是否变化。

tools
  tools[] 是否变化。

messages
  本轮和上一轮 messages[] 的结构化 diff。
```

## 第三步：重点看 `messages`

`messages` 是最重要的部分，因为 Claude Code harness 的主要动态变化都体现在这里。

典型结构：

```json
"messages": {
  "previous_count": 15,
  "current_count": 17,
  "common_prefix_count": 14,
  "append_only": false,
  "added_count": 3,
  "removed_or_rewritten_count": 1,
  "reset_or_rewrite_suspected": true,
  "added": [],
  "removed_or_rewritten": []
}
```

字段解释：

```text
previous_count
  上一个 request 中 messages[] 的数量。

current_count
  当前 request 中 messages[] 的数量。

common_prefix_count
  两个 request 从 messages[0] 开始，有多少条 message 完全相同。

append_only
  是否只是单纯在上一轮 messages 后面追加。

added_count
  当前 request 从第一个不同点开始，新增或替换出来的 message 数量。

removed_or_rewritten_count
  上一轮 request 从第一个不同点开始，被当前 request 替换掉的 message 数量。

reset_or_rewrite_suspected
  如果不是 append-only，就标记为 true。

added
  当前 request 中新增/替换出来的 message 摘要。

removed_or_rewritten
  上一轮中被替换掉的 message 摘要。
```

## `common_prefix_count` 怎么理解

如果：

```json
"common_prefix_count": 14
```

表示：

```text
message[0] 到 message[13] 在两轮 request 中完全一样
```

从 `message[14]` 开始，两轮 request 出现差异。

所以分析顺序是：

```text
1. 看 common_prefix_count，找到第一个变化位置
2. 看 removed_or_rewritten，理解上一轮尾部哪些内容被替换
3. 看 added，理解当前轮新增/替换进来了什么
```

## 第四步：重点看 `added`

`added` 最能说明当前轮 Claude Code 加了什么上下文。

每个 added message 形如：

```json
{
  "index": 15,
  "role": "assistant",
  "content_types": ["thinking", "text"],
  "text_chars": 684,
  "preview": "当前接入的 LLM provider 共 3 个...",
  "tool_use_ids": [],
  "tool_result_ids": []
}
```

字段解释：

```text
index
  这条 message 在当前 request.messages[] 中的位置。

role
  user / assistant 等角色。

content_types
  message content block 类型，例如 text、thinking、tool_use、tool_result。

text_chars
  文本字符数。

preview
  文本预览。

tool_use_ids
  assistant 发起的工具调用 id。

tool_result_ids
  user tool_result 对应的 tool_use_id。
```

## 如何判断新增 message 的类型

可以用下面的规则粗略判断：

```text
role=user + content_types 包含 text + preview 是用户自然语言
  => 用户真实输入

role=assistant + content_types 包含 tool_use
  => 模型发起工具调用

role=user + content_types 包含 tool_result
  => 工具结果被回灌进下一轮 request

role=assistant + content_types 包含 text
  => 上一轮 assistant 的自然语言回复进入历史

role=assistant + content_types 包含 thinking
  => thinking 摘要或 thinking block 被保留进上下文

role=user + preview 以 [SUGGESTION MODE...] 开头
  => Claude Code 注入的 suggestion mode 请求

role=user + preview 以 <system-reminder> 开头
  => Claude Code 注入的 system-reminder 或动态上下文
```

## 第五步：看 `removed_or_rewritten`

`removed_or_rewritten` 不是说内容一定被永久删除。它只是表示：

```text
从第一个不同位置开始，上一轮 request 的尾部不再和当前 request 完全一致
```

常见原因：

```text
tool_result 内容被补齐或改写
thinking block 变化
assistant message 被重新编码
suggestion mode 替换了尾部用户输入
context management 发生重写
session reset 或分支请求
```

所以不要只看到：

```json
"reset_or_rewrite_suspected": true
```

就立刻判断发生了 compaction。它只是结构提示，需要结合 `added` 和 `removed_or_rewritten` 的内容看。

## 第六步：看 system/tools/config 是否变化

在某个 `turns/000N.json` 里：

```json
"system": {
  "changed": true,
  "count": 4,
  "changed_indexes": [3]
}
```

表示：

```text
顶层 system[] 发生变化
变化的是 system[3]
```

这通常说明 Claude Code 的 session runtime 层发生变化，例如：

```text
动态提示变化
suggestion mode
环境上下文变化
session-specific 内容变化
```

tools：

```json
"tools": {
  "changed": false,
  "count": 8,
  "added": [],
  "removed": [],
  "changed_names": []
}
```

表示：

```text
本轮可用工具 schema 没变
```

config：

```json
"config": {
  "changed": false,
  "hash": "..."
}
```

表示 request 配置没有变化。配置包括：

```text
model
max_tokens
stream
thinking
betas
context_management
output_config
```

## 常用命令

看总览：

```bash
sed -n '1,220p' body-request-202605041115/session_diffs/timeline_diff.md
```

看第 9 轮新增了什么：

```bash
jq '.messages.added[] | {index, role, content_types, text_chars, preview, tool_use_ids, tool_result_ids}' \
  body-request-202605041115/session_diffs/turns/0009.json
```

看第 9 轮替换掉了什么：

```bash
jq '.messages.removed_or_rewritten[] | {index, role, content_types, text_chars, preview, tool_use_ids, tool_result_ids}' \
  body-request-202605041115/session_diffs/turns/0009.json
```

找所有 system 变化的轮次：

```bash
jq '.turn_diffs[] | select(.system.changed) | {index, request_file, changed_indexes:.system.changed_indexes}' \
  body-request-202605041115/session_diffs/session_diff_manifest.json
```

找所有 tools 变化的轮次：

```bash
jq '.turn_diffs[] | select(.tools.changed) | {index, request_file, added:.tools.added, removed:.tools.removed, changed_names:.tools.changed_names}' \
  body-request-202605041115/session_diffs/session_diff_manifest.json
```

找所有包含真实用户文本输入的新增 message：

```bash
jq '.turn_diffs[] | {
  turn: .index,
  added: [.messages.added[] | select(.role=="user" and (.content_types|index("text"))) | {index, preview}]
} | select(.added|length > 0)' \
  body-request-202605041115/session_diffs/session_diff_manifest.json
```

找所有 tool_use：

```bash
jq '.turn_diffs[] | {
  turn: .index,
  tool_uses: [.messages.added[] | select((.tool_use_ids|length) > 0) | {index, role, tool_use_ids}]
} | select(.tool_uses|length > 0)' \
  body-request-202605041115/session_diffs/session_diff_manifest.json
```

找所有 tool_result：

```bash
jq '.turn_diffs[] | {
  turn: .index,
  tool_results: [.messages.added[] | select((.tool_result_ids|length) > 0) | {index, role, tool_result_ids}]
} | select(.tool_results|length > 0)' \
  body-request-202605041115/session_diffs/session_diff_manifest.json
```

找所有疑似 rewrite/reset 的轮次：

```bash
jq '.turn_diffs[] | select(.messages.reset_or_rewrite_suspected) | {
  index,
  request_file,
  previous_count: .messages.previous_count,
  current_count: .messages.current_count,
  common_prefix_count: .messages.common_prefix_count,
  added_count: .messages.added_count,
  removed_or_rewritten_count: .messages.removed_or_rewritten_count
}' body-request-202605041115/session_diffs/session_diff_manifest.json
```

## 一个完整阅读例子

假设 `timeline_diff.md` 中有一行：

```text
| 9 | 15->17 | 14 | 3 | 1 | same | same | `5e29...request.json` |
```

阅读步骤：

1. 打开：

```bash
jq '.messages' body-request-202605041115/session_diffs/turns/0009.json
```

2. 看到：

```text
previous_count = 15
current_count = 17
common_prefix_count = 14
```

说明前 14 条 message 没变。

3. 看新增：

```bash
jq '.messages.added[] | {index, role, content_types, preview}' \
  body-request-202605041115/session_diffs/turns/0009.json
```

如果看到：

```text
message[14] user tool_result
message[15] assistant thinking+text
message[16] user text: 你觉得还有哪些地方需要改进，先不写代码，先讨论
```

就可以理解为：

```text
这一轮 request 把上一轮工具结果回灌进来了，
同时带入了 assistant 的自然语言回答，
然后追加了用户的新问题。
```

4. 看 system/tools：

```bash
jq '{system, tools, config}' body-request-202605041115/session_diffs/turns/0009.json
```

如果都是 `changed=false`，说明这一轮主要变化在 `messages[]`，不是系统提示或工具定义变化。

## 总结

阅读两轮 request 的变化关系时，按这个顺序：

```text
1. timeline_diff.md 找到值得深挖的 turn
2. turns/000N.json 看该 turn 的详细 diff
3. messages.common_prefix_count 定位第一个变化位置
4. messages.added 看当前轮新增了什么
5. messages.removed_or_rewritten 看上一轮尾部哪些内容被替换
6. system/tools/config 判断非 messages 的上下文是否变化
```

最重要的是：

```text
messages.added 才是观察 Claude Code 每轮 context 编排的核心入口。
```

