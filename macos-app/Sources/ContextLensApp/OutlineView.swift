import SwiftUI
import ContextLensCore

struct OutlineView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        if let session = model.selectedEntry?.session {
            List(selection: $model.selectedRequestID) {
                ForEach(session.turns) { turn in
                    Section("回合 \(turn.index) · \(turn.requests.count) req") {
                        ForEach(turn.requests) { req in
                            requestRow(req, flagged: session.ambiguities.contains { $0.file == basename(req.rawRequest) }).tag(req.id)
                        }
                    }
                }
                if !session.sidechannel.isEmpty {
                    Section("▹ 后台请求 (side-channel) · \(session.sidechannel.count)") {
                        ForEach(session.sidechannel) { req in
                            requestRow(req, flagged: session.ambiguities.contains { $0.file == basename(req.rawRequest) }).tag(req.id)
                        }
                    }
                }
                if !session.ambiguities.isEmpty {
                    Section("⚠︎ Ambiguities · \(session.ambiguities.count)") {
                        ForEach(session.ambiguities) { a in
                            VStack(alignment: .leading) {
                                Text(a.kind).font(.caption).bold()
                                Text([a.file, a.detail].compactMap { $0 }.joined(separator: " · "))
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .frame(minWidth: 200)
        } else {
            Text("Select a session").foregroundStyle(.secondary)
        }
    }

    private func requestRow(_ req: RequestRef, flagged: Bool) -> some View {
        HStack(spacing: 6) {
            Text("req \(req.index)").font(.system(.body, design: .monospaced))
            if flagged {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption2).foregroundStyle(.orange)
                    .help("此请求在 ambiguities 中（排序/配对存疑）")
            }
            Spacer()
            Text(req.orderConfidence).font(.caption2)
                .foregroundStyle(confidenceColor(req.orderConfidence))
        }
    }

    private func confidenceColor(_ conf: String) -> Color {
        if conf.hasPrefix("high") { return .green }
        if conf.hasPrefix("medium") { return .orange }
        if conf.hasPrefix("low") { return .red }
        return .secondary
    }

    private func basename(_ path: String) -> String {
        String(path.split(separator: "/").last ?? Substring(path))
    }
}
