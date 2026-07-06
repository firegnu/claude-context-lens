import SwiftUI
import ContextLensCore

struct SessionListView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        List(model.entries, selection: $model.selectedSessionID) { entry in
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.id).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
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
}
