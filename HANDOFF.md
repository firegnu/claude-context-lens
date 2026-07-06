# 会话交接 (HANDOFF)

> 日期:2026-07-06 · 分支:main(已推送公开 origin/main,tip `c3bce07`)· 状态:**两段式系统均已实现、打磨、发布**

## 快速恢复

一句话:「claude-context-lens 已产品化成两段——① Python 采集(`claude_lens/`)② macOS 展示 app(`macos-app/`),靠磁盘契约解耦,都在 main 且已推送公开 repo。app 可作为 `~/Applications/ContextLens.app` 双击打开。」

看 `README.md` 根(顶部两段式架构 + 端到端上手 + L1–L5 说明)即可上手;契约真相源在 `docs/superpowers/specs/2026-07-04-…`。

## 系统全貌

```
①  claude-lens (Python 采集)  →  ~/.claude-context-lens/sessions/  →  ②  macOS app (SwiftUI 展示)
```

- **① 采集端 `claude_lens/`**:`claude-lens run`(采集启动 claude,退出自动 ingest,单轮 `-p`/多轮交互)、`claude-lens ingest`(补摄取);产出磁盘契约(冻结)。
- **② 展示端 `macos-app/`**:纯 SwiftUI 只读查看器。`ContextLensCore`(Codable 模型 + `SessionStore` + `DiffEngine`,**12 单测**)+ `ContextLensApp`(三栏:sessions · 回合/请求 · 详情)。「构成」5 层(L1 config/L2 system/L3 messages/L4 tools/L5 response)点开读全文 + 预算条 + token chips;「变化」轮/请求粒度 diff。工具栏:刷新 + 文件夹选择器。**Dock 图标 + 菜单栏**(运行时 `AppIcon.make()`)。

## 怎么跑 app

- **双击版**:`macos-app/scripts/make-app.sh` → 装出 `~/Applications/ContextLens.app`,Spotlight/双击即开(本地构建,Gatekeeper 不拦)。改代码后重跑该脚本更新。
- **开发版**:`cd macos-app && swift run ContextLensApp`;测:`swift test`(12/12)。

## 本轮(deferred 打磨)完成的

Dock 图标+菜单栏、confidence 按级别配色、每请求 ambiguity 徽标、breakdown 加载占位、L3 tool_use_id/is_error 显示、diff 轮/请求粒度切换+不变层不展开、程序化 app 图标(放大镜+橙蓝紫层带)、`.app` 打包脚本。全部 ff 合并进 main 并推送。

## 待完成 / 已知

1. **唯一没做的小尾巴**:diff 里"任意手动 A/B 挑两请求比"(已做轮/请求粒度切换,请求级=选中 vs 前一个;自由双选器留后续)。
2. **⚠️ 公开 repo 隐私红线**:测试 fixture 必须是**合成假数据**(`macos-app/Tests/…/Fixtures/`),严禁提交真实采集内容(含 account_uuid 等 PII)。此前误提交过真数据、已改写历史清除。
3. **子项目一已知限制**(defer):重试/并行链假 `high:linked`;`messages_count` 排序在 auto-compact 边界乱序;thinking 正文遥测层不可得(硬限制,契约已标注)。

## 重要文件

- `macos-app/`(Swift app)· `claude_lens/`(Python 采集)· `tests/`(Python 25)· `macos-app/Tests/`(Swift 12,合成 fixture)
- `macos-app/scripts/make-app.sh` / `render-icon.swift` —— 打包 `.app` + 图标
- 采集:`python3 -m claude_lens.cli run -p "…"`(单轮)/ `run`(多轮)/ `ingest <raw-dir> --root …`
- 未合并的 worktree `deferred-ui`(分支 `worktree-deferred-ui`)仍在,内容已并入 main,可随时删。

## ⚠️ 未提交变更提醒

写本文件前工作树干净;本次文档更新(HANDOFF + 两份 README)是当前未提交变更,随即提交推送。
