import SwiftUI
import ContextLensCore

struct SessionListView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        List(model.entries, selection: $model.selectedSessionID) { entry in
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    sourceBadge(entry)
                    Text(entry.id).font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary).lineLimit(1)
                }
                if let s = entry.session {
                    Text(s.turns.first?.userMessagePreview ?? "—").lineLimit(1)
                    Text("\(s.counts.turns) 回合 · \(s.counts.requests) 请求")
                        .font(.caption2).foregroundStyle(.secondary)
                } else {
                    Text("加载失败").font(.caption).foregroundStyle(.red)
                }
            }.tag(entry.id)
        }
        .navigationTitle("Sessions")
        .frame(minWidth: 180)
    }

    /// Codex sessions carry `source == "codex"`; fall back to the id prefix when the
    /// session failed to decode, so a broken Codex session still reads as Codex.
    private func isCodex(_ entry: SessionEntry) -> Bool {
        if let src = entry.session?.source { return src == "codex" }
        return entry.id.hasPrefix("rollout-")
    }

    @ViewBuilder
    private func sourceBadge(_ entry: SessionEntry) -> some View {
        let codex = isCodex(entry)
        Text(codex ? "Codex" : "Claude")
            .font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background((codex ? Color.blue : Color.gray).opacity(0.22))
            .foregroundStyle(codex ? Color.blue : Color.secondary)
            .clipShape(Capsule())
    }
}
