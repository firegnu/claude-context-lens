# 子项目二 · macOS 展示 app —— 设计 spec

> 日期:2026-07-06 · 状态:设计已定稿(经可视化 mockup 逐屏确认)· 前置:子项目一契约已冻结(见 `2026-07-04-capture-service-and-data-contract-design.md`)

## 1. 背景与目标

子项目一(`claude-lens`)已把 Claude Code 的 wire 级 request/response 归一成一份**冻结的磁盘契约**(`session.json` + `raw/` + `derived/breakdown.json`)。本 spec 设计**子项目二**:一个原生 macOS app,**只读**消费该契约,把每一轮 context window 的**构成**和轮与轮之间的**变化**透明、可读地呈现出来。

**核心目的(承接子项目一 §2):研究 / 学习 prompt 构造** —— 一眼看清每次发给模型的 context window 由哪些层组成、每层的完整内容、以及轮间怎么增长变化。

## 2. 范围 / 非目标

**目标:**
- 从 `~/.claude-context-lens/sessions/` 读取并浏览多个 session(列表 + 单 session 深览)。
- **「构成」视图**:把单个请求(一次 context window)拆成完整层次,每层可点开读**完整正文**。
- **「变化」视图**:一个 diff 引擎,默认比相邻轮、可切请求级,呈现层级 delta + 块级增删改 + 文本级 diff。
- 显式暴露契约里的 `ambiguities`(排序/配对存疑)与 thinking 不可采集等限制。

**非目标(明确不做):**
- 采集(那是子项目一 `claude-lens` 的职责;app 不碰遥测、不启动 claude、不改写盘上数据)。
- 跨 session 搜索 / 聚合 / 成本分析 / 导出分享 / 编辑。
- 实时文件监听(MVP 用手动刷新代替)。
- 「变化」视图里自动配对"改动块"的高级启发式之外的智能(见 §6)。

## 3. 架构总览

```
磁盘契约(只读)                          macOS app
~/.claude-context-lens/sessions/
  <id>/session.json      ──读──>   ContextLensCore(纯 Swift,可单测)
  <id>/derived/*.json    ──懒加载─>    · Codable 模型(镜像 contract.py)
  <id>/raw/*.json        ──按需──>     · SessionStore(枚举/加载)
                                       · DiffEngine(纯函数)
                                          │
                                          ▼
                                     SwiftUI App(三栏 UI)
```

- **只读单向**:app 只读盘,唯一写的是自己的 UI 状态(选中项、展开状态),不落盘。
- **契约是唯一接口**:app 照 `2026-07-04` spec §5 做 Swift `Codable`,不依赖子项目一的任何 Python 代码。

## 4. 应用外壳 —— 三栏 `NavigationSplitView`

```
┌───────────┬──────────────────────┬─────────────────────────────────┐
│ Sessions  │ Turns / Requests     │  Detail  [ 构成 | 变化 ]         │
│ (列表)    │ (回合→请求大纲)      │                                 │
└───────────┴──────────────────────┴─────────────────────────────────┘
```

- **左栏 Sessions**:列出 sessions 根目录下每个 session —— session_id(时间戳)、首轮 `user_message_preview`、`counts`(回合/请求数)。选中 → 加载该 session。顶部一个刷新按钮重扫目录。
- **中栏 Turns / Requests**:两级大纲。回合(`turns[]`)可展开为其请求(`requests[]`),请求显示 index + `order_confidence`。**后台请求(`sidechannel[]`)单独一组、置底、默认折叠**,带 ⓘ 说明。选中一个请求 → 右栏「构成」;选中/框选两个(或两轮)→ 右栏「变化」。
- **右栏 Detail**:顶部 `构成 | 变化` 切换,内容见 §5 / §6。

## 5. 「构成」视图 —— 单个请求的完整层次

顶部一条**预算摘要**:横向堆叠条(system / messages / tools 字符占比)+ token chips(input / cache read / cache creation / output,来自 `usage`)。让"谁撑大了窗口"一眼可见。

其下是**五层**,每层一个可折叠区,点开某块即**就地展开显示完整解码正文**(等宽、可滚动、带元信息):

| 层 | 来源(breakdown.json) | 展开读到 |
|---|---|---|
| **L1 Request config** | `request_config` | model / max_tokens / thinking / betas / context_management / output_config / metadata / diagnostics 全文 |
| **L2 System prompt** | `system[]` | 每块 type / cache_control / chars + **完整正文** |
| **L3 Messages** | `messages[]` | 每个 content block:role/type/chars + 正文;`tool_use` 显示工具名/入参;`tool_result` 显示 tool_use_id/is_error;`thinking`→灰色占位「💭 思考内容不可采集」 |
| **L4 Tools** | `tools[]` | 每个工具 name + 描述字符数 + schema 字符数,展开读**完整 description + JSON schema** |
| **L5 Response** | `response` | 模型这次回复的内容块(文本;thinking 占位) |

- 通篇强调**字符/token 量级**(数字 + 条),服务于"研究什么塞满了窗口"。
- thinking 块按契约标注渲染为占位(正文不可采集,硬限制,见 2026-07-04 spec §5.2)。

## 6. 「变化 / diff」视图 —— 一个引擎、两级粒度

**比较对象选择**:默认比**相邻两轮的首请求**(轮 = 该轮首个请求代表其"用户新消息刚进来那一刻"的 context);顶部粒度开关可切到**请求级**(比任意相邻两请求,看工具循环内部怎么堆)。用户也可手动选定 A、B 两个请求。

**输出三层:**

1. **Δ 摘要**:总字符 delta、input/output token delta、块数 delta;以及哪些层"不变"(如 system / tools 常命中 cache 不变)。
2. **层级状态**:L1–L5 每层标 `不变 / +N 块 / 改动`。只有变化的层值得展开。
3. **块级 + 文本级**:展开某层 →
   - <span>`+` 新增块</span> / <span>`−` 删除块</span>(绿/红):点开读该块完整正文。
   - `~` 改动块(黄):点开是**红/绿文本级 diff**。

**Diff 引擎(纯函数 `diff(Breakdown, Breakdown) -> LayerDiff[]`):**
- **块匹配**:对每层的块算**归一化内容 digest**(忽略 `cache_control`,复用 2026-07-04 spec §5.3 的 normalize 思路)。两侧 digest 都有 = 不变;只在 B = 新增;只在 A = 删除。
- **改动块识别(启发式,MVP 够用)**:对**位置稳定的层**(L1 config、L2 system、L4 tools —— 数量/顺序基本不变),按位置对齐;对齐槽位 digest 不同 → 标 `改动` + 文本 diff。这正好覆盖"注入的 system-reminder / context_management 每轮更新"这类原地变化。
- **Messages 层**通常是**追加式增长**(新用户消息 + 上轮助手回复 + 工具循环结果并入历史),以"新增块"为主呈现。
- **兜底**:任意两个块用户都能手动"文本 diff",不依赖自动配对。
- 文本 diff 用标准行级 LCS diff(自实现或 Foundation 内建,无外部依赖)。

## 7. 数据层(ContextLensCore)

纯 Swift 库,不含 UI,可 `swift test`:

- **Codable 模型**镜像契约:`Session`(含 `counts`/`turns`/`sidechannel`/`ambiguities`)、`Turn`、`RequestRef`(含 `is_sidechannel`/`order_confidence`/`usage`/`totals`)、`Ambiguity`(`kind`/`file`/`detail`)、`Breakdown`(`request_config`/`system`/`messages`/`tools`/`response`/`usage`/`totals`)、各 `Block` 类型。
- **宽容解码**:未知键忽略、缺失可空字段容错(契约以后加字段不崩;`raw_response`/`usage` 可为 null)。
- **SessionStore**:枚举 session 目录(只解码 `session.json` 供列表),按需**懒加载** `derived/*.breakdown.json` 与 `raw/*.json`(相对路径基于 session 目录解析)。
- **DiffEngine**:§6 的纯函数,输入两份 `Breakdown`,输出结构化 diff。

## 8. 错误处理

- `session.json` 缺失/损坏 → 该 session 在列表里标"加载失败",不崩溃、不影响其他 session。
- `breakdown.json` / `raw` 缺失 → 对应层显示占位提示。
- **显式暴露 `ambiguities`**:请求项旁小徽标 + 一个可查看的列表(排序/配对/损坏/schema 存疑),让契约的不确定性可见。
- 空 session(无请求)→ 正常显示为"空",不报错。
- 手动刷新按钮重扫根目录(不做实时监听)。

## 9. 测试

- **金标解码测试**:拿 `~/claude-otel/bodies-20260504-111512` 摄取出的真实 `session.json` + 一份 `breakdown.json` 作为 fixture,验 Codable 解码正确(层数、块类型、thinking 占位、sidechannel、ambiguities)。
- **DiffEngine 单测**:构造 breakdown 对,覆盖:纯追加(新增块)、位置稳定层的原地改动、删除、不变、Δ 计数、文本级 diff。
- **SessionStore 单测**:临时目录放几个 session,验枚举/懒加载/损坏容错。
- UI 层不强求自动化测试(SwiftUI 手动验收)。

## 10. 技术选型

- **SwiftUI + macOS 14(Sonoma)+**,`NavigationSplitView` 三栏。
- **无外部依赖**(diff、JSON 全用标准库)。
- **工程结构**:SwiftPM 包 `ContextLensCore`(模型 + store + diff,可单测)+ 一个瘦 SwiftUI app target 依赖它。核心逻辑与 UI 解耦,便于测试与推理。

## 11. 后续(不在本 spec)

- "之后的功能之后再说"(用户明确 defer):高级搜索/聚合、成本分析、导出、实时监听、更智能的改动块配对、thinking 的代理采集方案等,均待后续单独设计。
