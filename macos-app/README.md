# ContextLens (macOS viewer)

Read-only SwiftUI viewer for the claude-context-lens on-disk contract. Requires
macOS 14+, no third-party dependencies.

On launch it reads the default root `~/.claude-context-lens/sessions/`; use the
**folder** toolbar button to point it at any other sessions root. Populate it
first from subproject one: `claude-lens run …` for Claude, `claude-lens sync-codex`
for Codex. Both sources render identically here — the session list tags each with a
blue **Codex** / coral **Claude** badge.

## Install (double-clickable app)
    macos-app/scripts/make-app.sh                 # → ~/Applications/ContextLens.app
    macos-app/scripts/make-app.sh /Applications   # → /Applications (system-wide)

Then open it from Spotlight (`ContextLens`), Finder, or Launchpad — or
`open ~/Applications/ContextLens.app`. It has its own Dock icon and menu bar.
Re-run the script after code changes to update the installed app. (Built
locally, so Gatekeeper does not block it.)

## Run from source (dev)
    cd macos-app && swift run ContextLensApp
    cd macos-app && swift test

## What it shows
- **构成 (composition)** — a request's context window as five layers you can
  drill into: L1 request config · L2 system prompt · L3 messages · L4 tools ·
  L5 response, plus a char/token budget header. `thinking` blocks show a
  placeholder (redacted at capture).
- **变化 (diff)** — what changed between two context windows, at `轮` (adjacent
  turns) or `请求` (adjacent requests) granularity: per-layer Δ summary, block
  add/remove/change, and a text-level diff.
- **Ambiguities** — honesty flags the contract carries, listed in the outline.
  Codex sessions surface their fidelity gaps here: reasoning is an `available:false`
  placeholder (server-encrypted), tools are flagged unavailable (no schema in the
  rollout), and reconstruction / compaction / multi-agent notes appear. Claude
  sessions surface capture ambiguities the same way.

## Layout
- `ContextLensCore` — Codable models, SessionStore, DiffEngine (15 unit tests,
  incl. Codex session/breakdown decode).
- `ContextLensApp` — three-pane SwiftUI app (sessions · turns/requests · detail).
- `scripts/make-app.sh`, `scripts/render-icon.swift` — package the `.app` + icon.
