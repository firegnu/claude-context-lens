import Foundation

public enum DiffLayer: String, CaseIterable {
    case config, system, messages, tools, response
}

public struct DiffBlock: Equatable {
    public let identity: String
    public let content: String
    public let label: String
    public let chars: Int
}

public struct DiffLayerResult: Identifiable {
    public let layer: DiffLayer
    public let added: [DiffBlock]
    public let removed: [DiffBlock]
    public let changed: [(before: DiffBlock, after: DiffBlock)]
    public let unchangedCount: Int
    public var id: String { layer.rawValue }
    public var hasChange: Bool { !added.isEmpty || !removed.isEmpty || !changed.isEmpty }
}

public struct DiffSummary {
    public let charDelta: Int
    public let addedBlocks: Int
    public let removedBlocks: Int
    public let changedBlocks: Int
}

public struct BreakdownDiff {
    public let layers: [DiffLayerResult]
    public let summary: DiffSummary
}

public enum TextDiffKind { case equal, insert, delete }
public struct TextDiffLine: Equatable {
    public let kind: TextDiffKind
    public let text: String
}

public enum DiffEngine {
    public static func blocks(_ b: Breakdown, layer: DiffLayer) -> [DiffBlock] {
        switch layer {
        case .config:
            return b.requestConfig.sorted { $0.key < $1.key }.map {
                DiffBlock(identity: $0.key, content: $0.value.displayString, label: $0.key,
                          chars: $0.value.displayString.count)
            }
        case .system:
            return b.system.map {
                DiffBlock(identity: "system[\($0.index)]", content: $0.text,
                          label: "system[\($0.index)]", chars: $0.chars)
            }
        case .messages:
            return b.messages.map {
                DiffBlock(identity: $0.text, content: $0.text,
                          label: "\($0.role ?? "?")·\($0.type ?? "?")", chars: $0.chars)
            }
        case .tools:
            return b.tools.map {
                let content = ($0.description ?? "") + "\n" + ($0.inputSchema?.displayString ?? "")
                return DiffBlock(identity: $0.name ?? "tool[\($0.index)]", content: content,
                                 label: $0.name ?? "tool[\($0.index)]",
                                 chars: $0.descriptionChars + $0.schemaChars)
            }
        case .response:
            return (b.response ?? []).map {
                DiffBlock(identity: "response[\($0.index)]", content: $0.text,
                          label: "\($0.type ?? "?")", chars: $0.chars)
            }
        }
    }

    /// When matchByIdentity is true, blocks are paired by `identity` and a differing
    /// `content` counts as "changed". When false (append-heavy messages), blocks are
    /// paired by content equality, so a content change appears as remove+add.
    public static func diffLayer(_ a: [DiffBlock], _ b: [DiffBlock],
                                 layer: DiffLayer, matchByIdentity: Bool) -> DiffLayerResult {
        var added: [DiffBlock] = []
        var removed: [DiffBlock] = []
        var changed: [(before: DiffBlock, after: DiffBlock)] = []
        var unchanged = 0

        if matchByIdentity {
            let aByID = Dictionary(a.map { ($0.identity, $0) }, uniquingKeysWith: { x, _ in x })
            let bByID = Dictionary(b.map { ($0.identity, $0) }, uniquingKeysWith: { x, _ in x })
            for blk in b {
                if let old = aByID[blk.identity] {
                    if old.content == blk.content { unchanged += 1 }
                    else { changed.append((before: old, after: blk)) }
                } else { added.append(blk) }
            }
            for blk in a where bByID[blk.identity] == nil { removed.append(blk) }
        } else {
            var aCounts: [String: Int] = [:]
            for blk in a { aCounts[blk.content, default: 0] += 1 }
            for blk in b {
                if let c = aCounts[blk.content], c > 0 { aCounts[blk.content] = c - 1; unchanged += 1 }
                else { added.append(blk) }
            }
            var bCounts: [String: Int] = [:]
            for blk in b { bCounts[blk.content, default: 0] += 1 }
            var seen: [String: Int] = [:]
            for blk in a {
                seen[blk.content, default: 0] += 1
                if seen[blk.content]! > (bCounts[blk.content] ?? 0) { removed.append(blk) }
            }
        }
        return DiffLayerResult(layer: layer, added: added, removed: removed,
                               changed: changed, unchangedCount: unchanged)
    }

    public static func diff(_ a: Breakdown, _ b: Breakdown) -> BreakdownDiff {
        var layers: [DiffLayerResult] = []
        for layer in DiffLayer.allCases {
            layers.append(diffLayer(blocks(a, layer: layer), blocks(b, layer: layer),
                                    layer: layer, matchByIdentity: layer != .messages))
        }
        let charsA = a.totals.systemChars + a.totals.messageChars
            + a.totals.toolDescriptionChars + a.totals.toolSchemaChars
        let charsB = b.totals.systemChars + b.totals.messageChars
            + b.totals.toolDescriptionChars + b.totals.toolSchemaChars
        let summary = DiffSummary(
            charDelta: charsB - charsA,
            addedBlocks: layers.reduce(0) { $0 + $1.added.count },
            removedBlocks: layers.reduce(0) { $0 + $1.removed.count },
            changedBlocks: layers.reduce(0) { $0 + $1.changed.count })
        return BreakdownDiff(layers: layers, summary: summary)
    }

    public static func textDiff(_ a: String, _ b: String) -> [TextDiffLine] {
        let x = a.components(separatedBy: "\n")
        let y = b.components(separatedBy: "\n")
        let n = x.count, m = y.count
        var lcs = Array(repeating: Array(repeating: 0, count: m + 1), count: n + 1)
        for i in stride(from: n - 1, through: 0, by: -1) {
            for j in stride(from: m - 1, through: 0, by: -1) {
                lcs[i][j] = x[i] == y[j] ? lcs[i + 1][j + 1] + 1
                                         : max(lcs[i + 1][j], lcs[i][j + 1])
            }
        }
        var out: [TextDiffLine] = []
        var i = 0, j = 0
        while i < n && j < m {
            if x[i] == y[j] { out.append(.init(kind: .equal, text: x[i])); i += 1; j += 1 }
            else if lcs[i + 1][j] >= lcs[i][j + 1] { out.append(.init(kind: .delete, text: x[i])); i += 1 }
            else { out.append(.init(kind: .insert, text: y[j])); j += 1 }
        }
        while i < n { out.append(.init(kind: .delete, text: x[i])); i += 1 }
        while j < m { out.append(.init(kind: .insert, text: y[j])); j += 1 }
        return out
    }
}
