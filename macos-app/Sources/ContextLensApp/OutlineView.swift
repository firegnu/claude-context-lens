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
                            requestRow(req).tag(req.id)
                        }
                    }
                }
                if !session.sidechannel.isEmpty {
                    Section("▹ 后台请求 (side-channel) · \(session.sidechannel.count)") {
                        ForEach(session.sidechannel) { req in
                            requestRow(req).tag(req.id)
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

    private func requestRow(_ req: RequestRef) -> some View {
        HStack {
            Text("req \(req.index)").font(.system(.body, design: .monospaced))
            Spacer()
            Text(req.orderConfidence).font(.caption2).foregroundStyle(.green)
        }
    }
}
