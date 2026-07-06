import Foundation
import ContextLensCore

enum DetailMode: String, CaseIterable { case composition = "构成", diff = "变化" }
enum DiffGranularity: String, CaseIterable { case turn = "轮", request = "请求" }

@MainActor
final class AppModel: ObservableObject {
    @Published var entries: [SessionEntry] = []
    @Published var selectedSessionID: String?
    @Published var selectedRequestID: String?
    @Published var mode: DetailMode = .composition
    @Published var diffGranularity: DiffGranularity = .turn
    @Published private(set) var root: URL
    private var breakdownCache: [String: Breakdown] = [:]

    private(set) var store: SessionStore

    init(store: SessionStore = SessionStore()) {
        self.store = store
        self.root = store.root
        reload()
    }

    func reload() {
        entries = store.listSessions()
        if selectedSessionID == nil { selectedSessionID = entries.first?.id }
    }

    /// Point the app at a different sessions root and reload from scratch.
    func openRoot(_ url: URL) {
        store = SessionStore(root: url)
        root = url
        breakdownCache.removeAll()
        selectedSessionID = nil
        selectedRequestID = nil
        reload()
    }

    var selectedEntry: SessionEntry? {
        entries.first { $0.id == selectedSessionID }
    }

    var selectedRequest: RequestRef? {
        guard let s = selectedEntry?.session else { return nil }
        let all = s.turns.flatMap(\.requests) + s.sidechannel
        return all.first { $0.id == selectedRequestID }
    }

    func breakdown(for req: RequestRef) -> Breakdown? {
        let key = "\(selectedSessionID ?? "")|\(req.breakdown)"
        if let cached = breakdownCache[key] { return cached }
        guard let dir = selectedEntry?.directory else { return nil }
        guard let bd = try? store.loadBreakdown(sessionDir: dir, relativePath: req.breakdown)
        else { return nil }
        breakdownCache[key] = bd
        return bd
    }

    /// Default comparison: first request of the turn containing the selection,
    /// vs first request of the next turn. Falls back to nil if unavailable.
    var defaultComparePair: (a: RequestRef, b: RequestRef)? {
        guard let s = selectedEntry?.session else { return nil }
        let turns = s.turns
        guard turns.count >= 2 else { return nil }
        // find turn index of current selection (default 0)
        let selReq = selectedRequestID
        let idx = turns.firstIndex { $0.requests.contains { $0.id == selReq } } ?? 0
        let aTurn = turns[min(idx, turns.count - 2)]
        let bTurn = turns[min(idx, turns.count - 2) + 1]
        guard let a = aTurn.requests.first, let b = bTurn.requests.first else { return nil }
        return (a, b)
    }

    /// The pair the diff view compares, per the current granularity.
    var comparePair: (a: RequestRef, b: RequestRef)? {
        switch diffGranularity {
        case .turn: return defaultComparePair
        case .request: return adjacentRequestPair
        }
    }

    /// Request-level: the request before the selection vs the selection itself
    /// (shows what this request added — e.g. within a tool loop).
    var adjacentRequestPair: (a: RequestRef, b: RequestRef)? {
        guard let s = selectedEntry?.session else { return nil }
        let ordered = s.turns.flatMap(\.requests).sorted { $0.index < $1.index }
        guard ordered.count >= 2 else { return nil }
        if let selID = selectedRequestID,
           let pos = ordered.firstIndex(where: { $0.id == selID }), pos > 0 {
            return (ordered[pos - 1], ordered[pos])
        }
        return (ordered[0], ordered[1])
    }
}
