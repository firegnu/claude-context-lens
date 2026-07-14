# 会话交接 (HANDOFF)

> 日期:2026-07-14 · 分支:main · 状态:**两段式系统 + Codex 支持均已实现并打磨;app 已装 `/Applications`**

## 快速恢复

一句话:「claude-context-lens 已产品化成两段——① Python 采集(`claude_lens/`)② macOS 展示 app(`macos-app/`),靠磁盘契约解耦。采集端支持**两个源**:Claude(实时 OTel)+ Codex(事后读 rollout)。app 零改动即可并排浏览两者,列表用蓝(Codex)/橙(Claude)徽章区分。」

看 `README.md` 根(两段式 + Codex 命令 + L1–L5)即可上手。

## 系统全貌

```
①  claude-lens (Python 采集)  →  ~/.claude-context-lens/sessions/  →  ②  macOS app (SwiftUI 展示)
   Claude OTel body / Codex rollout        统一契约(冻结)
```

- **① 采集端 `claude_lens/`**:
  - Claude:`claude-lens run`(采集启动,单轮 `-p`/多轮交互)、`claude-lens ingest`(补摄取)。
  - Codex:`claude-lens sync-codex`(批量增量同步)、`ingest-codex`(单个)、`list-codex`(发现)。读 `~/.codex/sessions/**/rollout-*.jsonl` → 同一契约(`codex_ingest.py` + `codex_breakdown.py`)。
- **② 展示端 `macos-app/`**:纯 SwiftUI 只读查看器。三栏(sessions · 回合/请求 · 详情)。「构成」5 层 + 预算条;「变化」轮/请求 diff;来源徽章;Ambiguities 区显示保真度标注。

## 怎么跑 app

- **双击版**:`macos-app/scripts/make-app.sh [DEST]` → 装出 `.app`(默认 `~/Applications`,传 `/Applications` 装系统级)。**当前已装 `/Applications/ContextLens.app`**。改代码后重跑该脚本更新。
- **开发版**:`cd macos-app && swift run ContextLensApp`;测:`swift test`(15/15)。

## Codex 支持(本轮完成)

方案 A(读 rollout → 现有冻结契约,app 零改动)。7 个 ticket:骨架 → 稳健吞真实 rollout → 回合切分 → per-model-call 五层 breakdown → compaction 安全姿态 → multi-agent 检测标记 → CLI。均合并 main。

**启动 app 后又修的**(合成 fixture 太干净、真实 shape 更复杂,让 Swift decoder 挂——前 6 轮 Python-only review 没抓到):
- `raw_request: null` vs 非 optional Swift `String` → 给 `""`。
- `base_instructions` 真实是 `{"text":…}` dict → 提取 `.text`;`codex_breakdown` 所有 text 过 `_as_text` 兜底(根本防御)。
- 来源徽章(session `source` 字段 + Swift 解码 + 蓝/橙 badge)。
- `sync-codex` 批量增量同步(存在即跳过、空会话删除、`--limit` 最新优先)。

**关键教训(已存 memory):契约有两个消费者——Python `validate_session` 只查 key 存在,Swift Codable 严格。改契约映射后必须 `cd macos-app && swift test`,并用真实会话端到端验证(不只信合成 fixture)。**

## 已知限制 / 待完成

1. **Codex 保真度差距**(契约已标注、app Ambiguities 可见):reasoning 加密占位、工具 schema 缺(L4 空)、L3 是 per-call 局部非完整重建、compaction 标边界不重建、multi-agent 检测即标记不重建(单 agent 不受影响)。
2. **⚠️ 公开 repo 隐私红线**:测试 fixture 必须**合成假数据**(`tests/`、`macos-app/Tests/…/Fixtures/`),严禁提交真实采集内容(PII)。真实 Codex 会话只在本地 store,不入库。
3. Claude 侧旧已知(defer):重试/并行链假 `high:linked`;thinking 正文遥测层不可得(硬限制,契约已标注)。

## 重要文件

- `claude_lens/`(Python 采集,含 `codex_ingest.py` + `codex_breakdown.py`)· `macos-app/`(Swift app)· `tests/`(Python 76)· `macos-app/Tests/`(Swift 15,合成 fixture)
- `macos-app/scripts/`:`make-app.sh`(打包 `.app`)· `gen-codex-fixture.py`(从真实 ingest 生成 Swift 解码 fixture)· `render-icon.swift`
- 采集命令:Claude `claude-lens run -p "…"` / `ingest`;Codex `claude-lens sync-codex [--limit N]` / `ingest-codex <rollout>` / `list-codex`

## ⚠️ 未提交变更提醒

本次文档更新(README + macos-app/README + HANDOFF)是当前未提交变更,随即提交并推送 origin/main(本轮所有 Codex + app 修复 commit 一并推送)。
