import SwiftUI
import ContextLensCore

struct DiffView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text("粒度").font(.caption).foregroundStyle(.secondary)
                Picker("粒度", selection: $model.diffGranularity) {
                    ForEach(DiffGranularity.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }.pickerStyle(.segmented).labelsHidden().frame(maxWidth: 140)
                Spacer()
            }.padding(8)
            Divider()
            content
        }
    }

    @ViewBuilder private var content: some View {
        if let pair = model.comparePair,
           let a = model.breakdown(for: pair.a), let b = model.breakdown(for: pair.b) {
            let d = DiffEngine.diff(a, b)
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text("比较 req\(pair.a.index) → req\(pair.b.index)"
                         + (model.diffGranularity == .turn ? "（相邻轮首请求）" : "（相邻请求）"))
                        .font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                    summary(d.summary)
                    ForEach(d.layers) { layer in LayerDiffRow(result: layer) }
                }.padding()
            }
        } else {
            Text(model.diffGranularity == .turn ? "需要至少两轮才能比较" : "需要至少两个请求才能比较")
                .foregroundStyle(.secondary).padding()
        }
    }

    private func summary(_ s: DiffSummary) -> some View {
        HStack(spacing: 8) {
            chip("Δ chars \(s.charDelta >= 0 ? "+" : "")\(s.charDelta)", .green)
            chip("+\(s.addedBlocks) 块", .green)
            if s.changedBlocks > 0 { chip("~\(s.changedBlocks) 改动", .yellow) }
            if s.removedBlocks > 0 { chip("−\(s.removedBlocks) 块", .red) }
        }
    }

    private func chip(_ text: String, _ color: Color) -> some View {
        Text(text).font(.system(.caption, design: .monospaced))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(RoundedRectangle(cornerRadius: 8).fill(color.opacity(0.2)))
    }
}

struct LayerDiffRow: View {
    let result: DiffLayerResult
    @State private var open = false
    var body: some View {
        Group {
            if result.hasChange {
                DisclosureGroup(isExpanded: $open) {
                    ForEach(Array(result.added.enumerated()), id: \.offset) { _, blk in
                        blockLine("+", blk.label, blk.content, .green)
                    }
                    ForEach(Array(result.changed.enumerated()), id: \.offset) { _, pair in
                        ChangedBlock(before: pair.before, after: pair.after)
                    }
                    ForEach(Array(result.removed.enumerated()), id: \.offset) { _, blk in
                        blockLine("−", blk.label, blk.content, .red)
                    }
                } label: { rowLabel }
            } else {
                rowLabel
            }
        }.padding(8).background(RoundedRectangle(cornerRadius: 7).stroke(.quaternary))
    }

    private var rowLabel: some View {
        HStack {
            Text(layerTitle).bold()
            Spacer()
            Text(badge).font(.caption).foregroundStyle(result.hasChange ? .primary : .secondary)
        }
    }

    private var layerTitle: String {
        switch result.layer {
        case .config: return "L1 · Request config"
        case .system: return "L2 · System prompt"
        case .messages: return "L3 · Messages"
        case .tools: return "L4 · Tools"
        case .response: return "L5 · Response"
        }
    }
    private var badge: String {
        if !result.hasChange { return "不变" }
        var parts: [String] = []
        if !result.added.isEmpty { parts.append("+\(result.added.count)") }
        if !result.changed.isEmpty { parts.append("~\(result.changed.count)") }
        if !result.removed.isEmpty { parts.append("−\(result.removed.count)") }
        return parts.joined(separator: " ")
    }

    private func blockLine(_ mark: String, _ label: String, _ content: String, _ color: Color) -> some View {
        VStack(alignment: .leading) {
            HStack {
                Text(mark).foregroundStyle(color).bold()
                Text(label).font(.system(.caption, design: .monospaced))
                Spacer()
            }
            Text(content).font(.system(.caption2, design: .monospaced))
                .lineLimit(2).foregroundStyle(.secondary)
        }.padding(.vertical, 2)
    }
}

struct ChangedBlock: View {
    let before: DiffBlock
    let after: DiffBlock
    @State private var open = false
    var body: some View {
        VStack(alignment: .leading) {
            Button { open.toggle() } label: {
                HStack {
                    Text("~").foregroundStyle(.yellow).bold()
                    Text(after.label).font(.system(.caption, design: .monospaced))
                    Spacer()
                    Text("changed").font(.caption2).foregroundStyle(.yellow)
                }
            }.buttonStyle(.plain)
            if open {
                let lines = DiffEngine.textDiff(before.content, after.content)
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                        Text((line.kind == .delete ? "- " : line.kind == .insert ? "+ " : "  ") + line.text)
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(line.kind == .delete ? .red : line.kind == .insert ? .green : .primary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }.padding(6).background(RoundedRectangle(cornerRadius: 5).fill(.black.opacity(0.15)))
            }
        }.padding(.vertical, 2)
    }
}
