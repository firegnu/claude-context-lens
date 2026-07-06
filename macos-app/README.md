# ContextLens (macOS viewer)

Read-only SwiftUI viewer for the claude-context-lens on-disk contract.

## Run
    cd macos-app
    swift run ContextLensApp

Requires macOS 14+. On launch it reads the default root
`~/.claude-context-lens/sessions/`; use the **folder** toolbar button to point
it at any other sessions root. Capture sessions first with `claude-lens run …`
(subproject one).

## Test
    cd macos-app && swift test

## Layout
- `ContextLensCore` — Codable models, SessionStore, DiffEngine (unit-tested).
- `ContextLensApp` — three-pane SwiftUI app (sessions · turns/requests · detail).
