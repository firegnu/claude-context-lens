import Foundation

public enum JSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null; return }
        if let b = try? c.decode(Bool.self) { self = .bool(b); return }
        if let n = try? c.decode(Double.self) { self = .number(n); return }
        if let s = try? c.decode(String.self) { self = .string(s); return }
        if let a = try? c.decode([JSONValue].self) { self = .array(a); return }
        if let o = try? c.decode([String: JSONValue].self) { self = .object(o); return }
        throw DecodingError.dataCorruptedError(in: c, debugDescription: "Unsupported JSON value")
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let n): try c.encode(n)
        case .bool(let b): try c.encode(b)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        case .null: try c.encodeNil()
        }
    }

    public var prettyString: String { render(indent: 0) }
    public var displayString: String { render(indent: -1) }

    private func render(indent: Int) -> String {
        let nl = indent < 0 ? "" : "\n"
        let pad = indent < 0 ? "" : String(repeating: "  ", count: indent + 1)
        let closePad = indent < 0 ? "" : String(repeating: "  ", count: indent)
        switch self {
        case .string(let s): return "\"\(s)\""
        case .number(let n):
            if let i = Int(exactly: n) { return String(i) }
            return String(n)
        case .bool(let b): return b ? "true" : "false"
        case .null: return "null"
        case .array(let a):
            if a.isEmpty { return "[]" }
            let items = a.map { pad + $0.render(indent: indent < 0 ? -1 : indent + 1) }
            return "[" + nl + items.joined(separator: "," + nl) + nl + closePad + "]"
        case .object(let o):
            if o.isEmpty { return "{}" }
            let items = o.sorted { $0.key < $1.key }.map {
                pad + "\"\($0.key)\": " + $0.value.render(indent: indent < 0 ? -1 : indent + 1)
            }
            return "{" + nl + items.joined(separator: "," + nl) + nl + closePad + "}"
        }
    }
}

public extension JSONValue {
    subscript(key: String) -> JSONValue? {
        if case let .object(dict) = self { return dict[key] }
        return nil
    }
    var intValue: Int? {
        if case let .number(n) = self { return Int(exactly: n.rounded()) }
        return nil
    }
}
