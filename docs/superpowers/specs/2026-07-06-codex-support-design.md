# 设计评估:给 claude-context-lens 加 Codex 支持

> 日期:2026-07-06 · 状态:评估完成,**决定采用方案 A(解析 rollout 日志)**;下次会话开工 · 前置:Claude 侧两段式系统已发布(见 `README.md`)

## 1. 目标

把现有"采集 → 磁盘契约 → macOS app 展示"的能力扩展到 **Codex CLI**(OpenAI 的编码 agent),让同一个 app 也能浏览 Codex 会话的 context window(构成 + 轮间变化)。

**核心洞见:契约解耦让展示端零改动。** 只要把 Codex 数据映射进现有的 `session.json` / `breakdown.json` 契约,**Swift app 一行都不用改**——它只认契约,不认数据来自谁。真正的工作全在采集 + 解析(Python)侧。

## 2. 关键差异:Codex 没有 `OTEL_LOG_RAW_API_BODIES`

Claude 侧能采集,是靠 Claude Code 一个特有功能:`OTEL_LOG_RAW_API_BODIES=file:…` 把 wire 级请求/响应 body dump 到文件。**Codex 没有等价开关。**

所以采集通道要重新想。好消息(实地验证,2026-07-06):**Codex 已经把每个会话写成 `~/.codex/sessions/rollout-*.jsonl`(及 `archived_sessions/`)**——不用另建采集基建,读它自己写的日志即可。

## 3. 两个方案

### 方案 A(**采用**):解析 Codex rollout 日志

读 `~/.codex/sessions/rollout-*.jsonl`(线性事件流),映射进契约。

- 采集:**零基建**——Codex 现成就写。只需一个"定位 + 读 rollout"的入口(类似 `claude-lens ingest`,但指向 rollout 文件)。
- 解析:新写 `codex_ingest.py` / `codex_breakdown.py`,把事件流映射成契约。

### 方案 B(**否决**):本地反向代理 API

把 Codex 的 `base_url` 指到本地反向代理(`127.0.0.1:port`),代理转发给真 OpenAI + 记录逐字 wire body。

- 形态:**反向代理**(客户端显式指过去 → 只截这一个客户端、这一个 API;不是系统级 MITM)。
- 收益:逐字 wire body(含工具 schema)、理论上能拿到未被客户端 redact 的内容。

## 4. 为什么选 A 不选 B —— 安全性是决定因素

即便是"安全做法"的反向代理,残余风险依然实打实:

1. **它握着你的 API key**——key 必须流经代理才能认证。一旦它记错日志(把 `Authorization` 头也落盘)、有 bug、或进程被攻破,泄露的是付费凭证,比会话内容更值钱。
2. **你所有 prompt/代码/会话在它那儿都是明文**——一个握着全部 LLM 流量的咽喉点。
3. **它在 API 请求路径上**——多一个必须永远正确、永远安全的常驻组件 = 新攻击面,理论上还能篡改往返流量。
4. 出站那腿证书校验一旦手滑关掉,等于给自己开真 MITM 的口子。
5. (更危险的正向 MITM 变体:装系统级自签 CA + `HTTP_PROXY`——能解密全机 HTTPS,**坚决不做**。)

为了"逐字 wire + 拿回 reasoning"这点边际收益,把 key 和全部流量交给请求路径上一个额外进程 —— **不划算**。

**对比"读日志"方式:**

| 采集方式 | 碰 API key | 拦网络流量 | 请求路径加组件 |
|---|---|---|---|
| Claude:读 OTEL dump(现状) | ❌ | ❌ | ❌ |
| **Codex:读 rollout(方案 A)** | ❌ | ❌ | ❌ |
| Codex:反向代理(方案 B) | ✅ 握 key | ✅ | ✅ |

方案 A 与现在 Claude 侧**同一个哲学**:只读、被动、零基建、不碰密钥。安全性与现状同级。**这是选 A 的决定性理由。**

## 5. Codex rollout 格式(实地探得,只看结构未看内容)

`rollout-*.jsonl` 每行一个事件,主要类型:

| 事件 `type` | `payload` 关键字段 | 映射到契约层 |
|---|---|---|
| `session_meta` | **base_instructions**、cli_version、model_provider、cwd、git、id | L2 系统提示(基座)+ 会话元信息 |
| `turn_context` | **model / effort / user_instructions / approval_policy / sandbox_policy / truncation_policy** | L1 request config + 用户指令 |
| `response_item` | role、content、`type`(=`message` / `reasoning`)、**`encrypted_content`**、summary | L3 消息 / reasoning(见限制) |
| `event_msg` | `type`(user_message / agent_message / agent_reasoning / **token_count**)、message、text、rate_limits | L3 事件 + usage(token_count) |

## 6. 契约映射(A 方案)

沿用现有 `session.json` / `breakdown.json` 形状,把 Codex 字段填进去:

- **L1 config** ← `turn_context`(model / effort / sandbox_policy / user_instructions …)
- **L2 system** ← `session_meta.base_instructions` + `turn_context.user_instructions`
- **L3 messages** ← `response_item`(message)+ `event_msg`(user/agent message);reasoning 块 → 占位
- **L4 tools** ← **大概率缺**(见限制)
- **L5 response** ← 该轮的 agent message / reasoning
- **usage** ← `event_msg.token_count`
- **排序/turns** ← rollout 本身**有序、带 timestamp**,不需要 Claude 那套 `previous_message_id` 配对+置信度重建;按 `event_msg` 的 user_message 切回合即可

## 7. 难度评估

| 组件 | 难度 | 说明 |
|---|---|---|
| Swift 展示端 | **0** | 契约不变,完全不动 |
| 采集通道 | **低** | 零基建,读现成 rollout;一个 ingest 入口 |
| ingest/breakdown 解析 | **中(主要工作量)** | 新 `codex_ingest.py`:事件流 → 契约。结构不同——Claude 是每请求一张完整快照;Codex 是 **transcript**,得沿流"重放"重建每次模型调用时的 context window |
| 排序/配对 | **低 ↓** | rollout 有序,省掉 Claude 的配对重建 |
| turn 切分 | **低-中** | 按 user_message 事件切 |
| 契约 | **低** | 映射即可 |

**总体:低-中。** 核心就一个 rollout 解析器。

## 8. 已知限制(诚实记录)

1. **reasoning 正文拿不到**:`response_item` 的 reasoning 是 `encrypted_content`(服务端加密),和 Claude 的 thinking redact 一个道理 → 只能占位。**方案 A 无解**(方案 B 也未必,因为是服务端加密)。
2. **L4 工具 schema 大概率缺**:rollout 记了工具**调用**(会作为 response_item 出现),但不一定记发给 API 的**工具定义/schema**。工具层可能为空或需另找来源。(这是 A 相对 Claude 逐字采集的保真差距;真要补,只能靠方案 B——但已否决。)
3. **是"重建"不是"逐字快照"**:rollout 是转录流,重建"第 N 次调用时的 context"是**推断**的,不像 Claude 有 API 请求体逐字 JSON。对"研究 prompt 构造"够用,wire 保真度低一档。

## 9. 组件结构(草图)

与 Claude 侧并行,复用契约:

```
claude_lens/
  codex_ingest.py       # 读 rollout-*.jsonl → 事件流 → 重建 per-call context → 写 session.json
  codex_breakdown.py    # 单次调用的 L1-L5 拆解(OpenAI/Codex 字段版)
  contract.py           # 复用:契约 schema 与读写(不变)
  cli.py                # 加入口,如 `claude-lens ingest-codex <rollout.jsonl>` 或自动发现 ~/.codex/sessions
```

## 10. 下次开工前要验证的未知

1. rollout 是否**完整**覆盖一次会话的所有轮/所有模型调用(还是有截断/compaction)。
2. 工具 schema 到底在不在 rollout 里(或 `~/.codex` 别处)——决定 L4 能不能填。
3. reasoning 的 `encrypted_content` 是否真的无法解(基本确定不可解,占位即可)。
4. `~/.codex/sessions/` 的目录结构 + `session_index.jsonl` 怎么用来定位/列会话(供 app 或 ingest 发现)。
5. 从 transcript **重建 per-model-call context** 的规则(每次调用 = 之前所有 item + 该轮 instructions/tools),保真到什么程度可接受。

## 11. 下一步

下次会话:对方案 A 的 Codex ingest 走一遍 brainstorming → spec → plan → 实现(可复用现有 subagent-driven 流程)。Swift 侧预期零改动;若映射需要契约加字段(如 `source: "codex"` 或标注 reasoning/tools 缺失),再在契约里补并保持 Claude 侧兼容。
