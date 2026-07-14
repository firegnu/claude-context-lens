import Foundation

public extension JSONDecoder {
    static var contract: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }
}

public struct Session: Codable {
    public let sessionId: String
    public let capturedAt: String
    public let launcherArgv: [String]?
    public let model: String?
    // "codex" for Codex-ingested sessions; nil for Claude (absence == Claude).
    public let source: String?
    public let counts: Counts
    public let turns: [Turn]
    public let sidechannel: [RequestRef]
    public let ambiguities: [Ambiguity]
}

public struct Counts: Codable {
    public let turns: Int
    public let requests: Int
    public let responses: Int
    public let sidechannel: Int
}

public struct Turn: Codable, Identifiable {
    public let index: Int
    public let userMessagePreview: String
    public let requests: [RequestRef]
    public var id: Int { index }
}

public struct RequestRef: Codable, Identifiable {
    public let index: Int
    public let rawRequest: String
    public let rawResponse: String?
    public let breakdown: String
    public let previousMessageId: String?
    public let orderConfidence: String
    public let isSidechannel: Bool
    public let usage: JSONValue?
    public let totals: Totals
    public var id: String { breakdown }
}

public struct Totals: Codable {
    public let systemChars: Int
    public let messageChars: Int
    public let toolChars: Int
}

public struct Ambiguity: Codable, Identifiable {
    public let kind: String
    public let file: String?
    public let detail: String?
    public var id: String { "\(kind):\(file ?? "")\(detail ?? "")" }
}
