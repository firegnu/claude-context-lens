# Opus 4.7 vs 4.8 — Claude Code 上下文对比

两份均来自 `run-claude-otel.sh` 采集的真实 raw body，cwd 同为 `multiLLM-providers`，首轮均为 `你好`。

| | 4.7 | 4.8 |
|---|---|---|
| model | `claude-opus-4-7` | `claude-opus-4-8` |
| cc_version | 2.1.126.88c | 2.1.158.5e6 |
| 采集日期 | 2026-05-04 | 2026-05-31 |
| source request | `9885e4e6-…request.json` | `4138e034-…request.json` |

> 注意：两次采集日期不同，因此 gitStatus、skills 清单、CLAUDE.md 等**动态部分**本就会有差异，不能算作版本差异。下文只把**真正由模型/harness 版本带来的结构性变化**列为结论，动态噪音单列说明。

---

## 1. 最大变化：system prompt 大幅瘦身（约 -64%）

system 字段都是 **4 个 block、缓存结构完全相同**（b0/b1 不缓存，b2 `global`，b3 会话级 `1h`），但正文体量骤减：

| block | 内容 | 4.7 字符 | 4.8 字符 | 变化 |
|---|---|---|---|---|
| 0 | 计费头 | 81 | 81 | — |
| 1 | `You are Claude Code…` | 57 | 57 | — |
| 2 | global 缓存核心 | 9,925 | **1,152** | **-88%** |
| 3 | 行为规范 + 环境 | 20,455 | **9,750** | **-52%** |
| **合计** | | **30,518** | **11,040** | **-64%** |

**信息没有消失，而是搬家了**：4.7 把 superpowers / skills / memory / MCP 等大量内容塞在 system 字段里；4.8 把这些移到了 **messages 层一条 `role=system` 的消息**（见第 3 点）。net 效果是 system 字段更精简、更稳定，利于跨会话缓存命中。

---

## 2. 启动注入结构重构：新增 `role=system` 消息

| | 4.7 | 4.8 |
|---|---|---|
| messages 数量（首轮） | 1 | 2 |
| roles | `[user]` | `[user, system]` |
| `你好` + CLAUDE.md | 都在 user 的 content blocks | 仍在 user |
| superpowers/skills/MCP/deferred tools | 在 user 的 `<system-reminder>` 里 | 移到独立的 `role=system` 消息（约 35,014 字符） |

4.7 是「所有注入塞进一条 user 消息」，4.8 改为「user 放真实输入 + 一条 system 消息放会话上下文」。这条 system 消息是**对话中途注入的 system**，对应新增的 beta `mid-conversation-system-2026-04-07`。

---

## 3. 工具集：8 → 10

```
4.7 (8): Agent Bash Edit Read ScheduleWakeup Skill ToolSearch Write
4.8 (10): …同上… + Workflow + AskUserQuestion
```

- **`Workflow`** — 多智能体编排（确定性 fan-out / pipeline，描述长达 ~18KB，是最大的工具）
- **`AskUserQuestion`** — 结构化向用户提问

无工具被移除。

---

## 4. Beta flags 新增

4.8 相比 4.7 新增 3 个 beta（无移除）：

| beta | 含义 |
|---|---|
| `mid-conversation-system-2026-04-07` | 允许在对话中途插入 system 消息（对应第 2 点） |
| `thinking-token-count-2026-05-13` | thinking token 计数 |
| `extended-cache-ttl-2025-04-11` | 更长的缓存 TTL |

`effort=xhigh`、`thinking=adaptive/summarized` 两版相同。

---

## 5. 回复行为差异

| | 4.7 | 4.8 |
|---|---|---|
| 对「你好」的回复 | `你好！有什么可以帮你的吗？`（纯问候） | 带 **thinking 块**，并主动读取项目 git 状态作答 |
| response content blocks | 1（text） | 2（thinking + text） |

4.8 即便面对一句简单问候，也会先 thinking、再结合当前项目上下文给出更主动的回答。

---

## 动态差异（非版本差异，仅供识别）

以下因两次采集的时间/会话不同而变化，**不应解读为 4.7→4.8 的改动**：
- `# Environment` 里的 OS 版本（25.4.0 → 25.5.0）、gitStatus 快照内容
- skills 清单、deferred tools 清单（随当时安装的插件/MCP 变化）
- CLAUDE.md 内容（用户全局配置随时间变化）

---

## 关联文件

- `4-7-system-prompt.md` / `4-8-system-prompt.md` — 各自合并后的 system prompt 正文
- `4-7-full-context.md` / `4-8-full-context.md` — 各自完整上下文窗口（system + tools + messages + 输出 + 配置附录）
