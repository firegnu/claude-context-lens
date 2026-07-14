# 为什么 Codex 的「系统提示」看起来比 Claude 大一个数量级

这个文档解释一个在 app / 契约里并排看两个来源时常见的误解:

> 「怎么 Claude 的 system prompt 比 GPT(Codex)少了那么多?」

**结论先行:Claude 的系统提示并没有真的少一个数量级。** 你看到的差是两件事叠出来的假象——(1) 拿一条 Agent SDK 的精简会话去比,(2) 两边的 `system_chars` 量的根本不是同一块东西。把口径对齐后,两边送给模型的指令总量**几乎一样大**。

---

## 一、实测数据

对 `~/.claude-context-lens/sessions/` 里已重建的会话,取每个请求的 L2(`system`)和 L4(`tools`)字符数:

| 会话 | 来源 | L2 `system_chars` | L4 `tools_chars` | 合计 |
|---|---|---:|---:|---:|
| `20260504-111512` | Claude(正常编码会话) | 30,518 | **46,008** | **76,526** |
| `20260706-135557` | Claude(Agent SDK,一句 `hi`) | 7,011 | 39,053 | 46,064 |
| `rollout-2026-07-10T18-15-07…` | Codex(单 agent) | **72,189** | 0(未采到) | 72,189 |

单看 L2:`7,011` vs `72,189` ≈ **10 倍**,这就是「少一个数量级」的来源。但这个比法有两处陷阱。

---

## 二、陷阱一:那条 7K 的 Claude 会话是异类

`20260706-135557` 不是正常的 Claude Code 编码会话:

- `system[1]` 的内容是 `You are a Claude agent, built on Anthropic's Claude Agent SDK.`
- billing header 里 `cc_entrypoint=sdk-`
- 整段对话就一句用户输入 `hi`,`counts.turns = 1`

这是通过 **Agent SDK** 起的一个精简会话,系统提示本身就短。正常的 Claude Code 会话(`20260504`)L2 就有 **30,518**。用 7K 去比 72K,是拿玩具会话比真实会话。

拿正常会话比:`30,518` vs `72,189` ≈ **2.4 倍**——已经不是数量级了。剩下的 2.4 倍由陷阱二解释。

---

## 三、陷阱二:两边的 `system_chars` 量的不是同一块东西

关键在于**工具定义放在哪个通道**,以及各自 `system_chars` 把哪些内容算了进去。

### Claude 侧:工具走独立通道,不计进 system

Claude 的请求体里 `system` 和 `tools` 是**两个独立字段**。`breakdown.py` 分别统计:

- `system_chars` 只数 `request_body["system"]`(系统提示本身)
- 工具 schema 在 `request_body["tools"]`,进 **L4**,计进 `tool_chars`,**不进 `system_chars`**

`20260504` 实测:system 30,518(4 块,末尾接的是 git status,**完整未被截断**)、tools 46,008(8 个工具:描述 39,720 + schema 6,288)。

也就是说,Claude 有 ~46K 的指令预算**停在 L4**,没算进 L2。

### Codex 侧:脚手架内联成 developer 文本,全压进 system

Codex 的 rollout **不带工具 schema**(L4 空、`tools_available: false`)。但 Codex 把大量框架脚手架当 **developer 角色的正文**塞进上下文,`codex_breakdown.py` 把 `base_instructions + 所有 developer 消息` 都算进 `system_chars`。

`rollout-2026-07-10…` 的 72,189 拆开是:

| 块 | 类型 | chars | 内容 |
|---|---|---:|---|
| [0] | `base_instructions` | 16,270 | `You are Codex, an agent based on GPT-5…` ← **真正对标 Claude 系统提示的部分** |
| [1] | `developer` | 53,891 | `<permissions_instructions>` … `<plugins_instructions>`(沙箱/权限/插件规则) |
| [2] | `developer` | 1,842 | agent-team 说明(`You are /root, the primary agent…`) |
| [3] | `developer` | 186 | `<multi_agent_mode>` |

注意:**Codex 真正的「系统提示」(base_instructions)只有 16K,比 Claude 的 30K 还小。** 撑起 72K 的是那条 53,891 的 developer 消息——沙箱、权限、插件规则等脚手架,在 Claude 那边是通过 harness / 工具层交付的,不作为系统提示正文出现。

### 把口径对齐:合计几乎相等

工具是「Codex 内联进 system-as-text、Claude 挂在独立 L4」的东西。把它算回来:

```text
Claude 20260504 : system 30,518 + tools 46,008 = 76,526
Codex  rollout  : system 72,189 + tools      0 = 72,189
```

**76.5K vs 72K——基本一样。** 差异不在「模型收到多少指令」,而在**指令放在哪个通道**:Claude 用 API 的结构化 `tools` 字段(→ L4),Codex 内联成 developer 正文(→ 混进 L2)。

---

## 四、这不是采集截断

一个容易先入为主的猜测是「Claude 的 system 被 OTEL 遥测层抹掉了」(类比 thinking 正文被抹)。**数据否掉了这个猜测**:`20260504` 的 30,518 是完整的四块系统提示,末尾正常收在 git status,没有截断痕迹。thinking 确实被遥测层抹成 `<REDACTED>`(见 `breakdown.py` 的 `THINKING_TYPES`),但**系统提示是逐字完整捕获的**。

所以这是**口径差**,不是**保真度差**。

---

## 五、对 app / 契约的影响与建议

并排看两个来源的「system 面板」时,当前口径有误导性:

- Codex 的 L4 是空的,它的工具/权限说明藏在 L2 的 developer 块里 → L2 虚高
- Claude 的 L4 挂着 46K 工具,L2 只有系统提示本身 → L2 虚低

直接比 L2 长度会得出「Claude 少一个数量级」的错误印象。**正确的比法是比 L2 + L4 合计**,或在解释时说明两边工具的归属不同。

可选的改进(未实施,供讨论):

- 在 Codex session 上加个 additive 标注,例如 `tools_inlined_in_system: true`,提示「本来源的工具说明混在 system 里、L4 为空」
- app 的对比视图里把「系统总量」显示为 **L2 + L4 合计**,而不是只显示 L2

---

## 六、如何自己复现

```bash
python3 - <<'PY'
import json, os, glob
root = os.path.expanduser("~/.claude-context-lens/sessions")
def load(p):
    with open(p) as f: return json.load(f)

for d in sorted(glob.glob(os.path.join(root, "*"))):
    sj = os.path.join(d, "session.json")
    if not os.path.exists(sj): continue
    name = os.path.basename(d)
    kind = "CODEX" if name.startswith("rollout-") else "CLAUDE"
    dv = os.path.join(d, "derived")
    bds = sorted(f for f in os.listdir(dv) if f.endswith(".breakdown.json"))
    if not bds: continue
    bd = load(os.path.join(dv, bds[0]))            # 第一个请求
    t = bd["totals"]
    sysc = t["system_chars"]
    toolc = t["tool_description_chars"] + t["tool_schema_chars"]
    print(f"{kind:6} {name:44} L2={sysc:7} L4={toolc:7} L2+L4={sysc+toolc:7}")
PY
```

要看某个 Codex 会话 L2 里到底是什么(base vs developer 各占多少):

```bash
python3 - <<'PY'
import json, os
root = os.path.expanduser("~/.claude-context-lens/sessions")
d = os.path.join(root, "rollout-2026-07-10T18-15-07-019f4b86-1a40-7eb2-9b68-2cfb36055b8c")
dv = os.path.join(d, "derived")
bd = json.load(open(os.path.join(dv, sorted(os.listdir(dv))[0])))
for s in bd["system"]:
    print(f"[{s['index']}] {s['type']:18} {s['chars']:7}  {s['text'][:80]!r}")
PY
```

---

## 关键事实源

- `claude_lens/breakdown.py` — Claude 侧 L2 来源(`request_body["system"]`)、工具归 L4、thinking 抹除
- `claude_lens/codex_breakdown.py` — Codex 侧 L2 = `base_instructions + developer_messages`、L4 空、`tools_available: false`
- 实测样本:`~/.claude-context-lens/sessions/`(2 条 Claude + 若干 Codex rollout)
