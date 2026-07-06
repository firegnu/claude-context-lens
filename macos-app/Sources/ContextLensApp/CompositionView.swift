import SwiftUI
import ContextLensCore

struct CompositionView: View {
    let breakdown: Breakdown

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                BudgetHeader(totals: breakdown.totals, usage: breakdown.usage)
                LayerDisclosure(title: "L1 · Request config", subtitle: configSummary) {
                    ForEach(breakdown.requestConfig.sorted { $0.key < $1.key }, id: \.key) { k, v in
                        FullTextRow(label: k, text: v.prettyString, chars: v.displayString.count)
                    }
                }
                LayerDisclosure(title: "L2 · System prompt · \(breakdown.system.count) 块",
                                subtitle: "\(breakdown.totals.systemChars) chars") {
                    ForEach(breakdown.system) { b in
                        FullTextRow(label: "system[\(b.index)]", text: b.text, chars: b.chars)
                    }
                }
                LayerDisclosure(title: "L3 · Messages · \(breakdown.messages.count) 条",
                                subtitle: "\(breakdown.totals.messageChars) chars") {
                    ForEach(breakdown.messages) { m in messageRow(m) }
                }
                LayerDisclosure(title: "L4 · Tools · \(breakdown.tools.count) 个",
                                subtitle: "desc \(breakdown.totals.toolDescriptionChars) · schema \(breakdown.totals.toolSchemaChars)") {
                    ForEach(breakdown.tools) { t in
                        FullTextRow(label: t.name ?? "tool[\(t.index)]",
                                    text: (t.description ?? "") + "\n\n" + (t.inputSchema?.prettyString ?? ""),
                                    chars: t.descriptionChars + t.schemaChars)
                    }
                }
                LayerDisclosure(title: "L5 · Response",
                                subtitle: "模型这次回复") {
                    ForEach(breakdown.response ?? []) { r in responseRow(r) }
                }
            }.padding()
        }
    }

    private var configSummary: String {
        let model = breakdown.requestConfig["model"]?.displayString ?? ""
        return model.replacingOccurrences(of: "\"", with: "")
    }

    @ViewBuilder private func messageRow(_ m: MessageBlock) -> some View {
        if m.type == "thinking" || m.type == "redacted_thinking" {
            HStack {
                Text("thinking").font(.caption).padding(2).background(.gray.opacity(0.2))
                Text("💭 思考内容不可采集").italic().foregroundStyle(.secondary)
            }
        } else {
            FullTextRow(label: messageLabel(m), text: m.text, chars: m.chars)
        }
    }

    private func messageLabel(_ m: MessageBlock) -> String {
        var parts = ["\(m.role ?? "?")·\(m.type ?? "?")"]
        if let name = m.toolName { parts.append(name) }
        if m.isError == true { parts.append("❌ error") }
        if let id = m.toolUseId { parts.append("#\(id.suffix(8))") }
        return parts.joined(separator: " ")
    }

    @ViewBuilder private func responseRow(_ r: ResponseBlock) -> some View {
        if r.type == "thinking" || r.type == "redacted_thinking" {
            Text("💭 思考内容不可采集").italic().foregroundStyle(.secondary)
        } else {
            FullTextRow(label: r.type ?? "?", text: r.text, chars: r.chars)
        }
    }
}

struct BudgetHeader: View {
    let totals: BreakdownTotals
    let usage: JSONValue?
    var body: some View {
        let sys = Double(totals.systemChars)
        let msg = Double(totals.messageChars)
        let tool = Double(totals.toolDescriptionChars + totals.toolSchemaChars)
        let sum = max(sys + msg + tool, 1)
        VStack(alignment: .leading, spacing: 4) {
            GeometryReader { geo in
                HStack(spacing: 0) {
                    Rectangle().fill(.orange).frame(width: geo.size.width * sys / sum)
                    Rectangle().fill(.blue).frame(width: geo.size.width * msg / sum)
                    Rectangle().fill(.purple).frame(width: geo.size.width * tool / sum)
                }
            }.frame(height: 14).clipShape(RoundedRectangle(cornerRadius: 4))
            HStack(spacing: 14) {
                Label("system \(totals.systemChars)", systemImage: "square.fill").foregroundStyle(.orange)
                Label("messages \(totals.messageChars)", systemImage: "square.fill").foregroundStyle(.blue)
                Label("tools \(Int(tool))", systemImage: "square.fill").foregroundStyle(.purple)
            }.font(.caption)
            if let usage {
                HStack(spacing: 6) {
                    if let v = usage["input_tokens"]?.intValue { TokenChip(label: "input", value: v) }
                    if let v = usage["cache_read_input_tokens"]?.intValue { TokenChip(label: "cache read", value: v) }
                    if let v = usage["cache_creation_input_tokens"]?.intValue { TokenChip(label: "cache create", value: v) }
                    if let v = usage["output_tokens"]?.intValue { TokenChip(label: "output", value: v) }
                }
            }
        }
    }
}

struct TokenChip: View {
    let label: String
    let value: Int
    var body: some View {
        HStack(spacing: 4) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text("\(value)").font(.system(.caption2, design: .monospaced))
        }
        .padding(.horizontal, 6).padding(.vertical, 2)
        .background(RoundedRectangle(cornerRadius: 5).fill(.gray.opacity(0.15)))
    }
}

struct LayerDisclosure<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder let content: () -> Content
    @State private var expanded = false
    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            content()
        } label: {
            HStack { Text(title).bold(); Spacer()
                Text(subtitle).font(.caption).foregroundStyle(.secondary) }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 7).stroke(.quaternary))
    }
}

struct FullTextRow: View {
    let label: String
    let text: String
    let chars: Int
    @State private var open = false
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Button { open.toggle() } label: {
                HStack {
                    Image(systemName: open ? "chevron.down" : "chevron.right").font(.caption2)
                    Text(label).font(.system(.caption, design: .monospaced))
                    Spacer()
                    Text("\(chars)").font(.caption2).foregroundStyle(.secondary)
                }
            }.buttonStyle(.plain)
            if open {
                ScrollView {
                    Text(text.isEmpty ? "—" : text)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }.frame(maxHeight: 240).padding(6)
                 .background(RoundedRectangle(cornerRadius: 5).fill(.black.opacity(0.15)))
            }
        }.padding(.vertical, 2)
    }
}
