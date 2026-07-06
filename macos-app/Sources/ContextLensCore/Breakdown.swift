import Foundation

public struct Breakdown: Codable {
    public let requestConfig: [String: JSONValue]
    public let system: [SystemBlock]
    public let messages: [MessageBlock]
    public let tools: [ToolDef]
    public let response: [ResponseBlock]?
    public let usage: JSONValue?
    public let totals: BreakdownTotals
}

public struct SystemBlock: Codable, Identifiable {
    public let index: Int
    public let type: String?
    public let cacheControl: JSONValue?
    public let chars: Int
    public let text: String
    public var id: Int { index }
}

public struct MessageBlock: Codable, Identifiable {
    public let messageIndex: Int
    public let contentIndex: Int
    public let role: String?
    public let type: String?
    public let chars: Int
    public let text: String
    public let toolUseId: String?
    public let toolName: String?
    public let isError: Bool?
    public let available: Bool?
    public var id: String { "\(messageIndex).\(contentIndex)" }
}

public struct ToolDef: Codable, Identifiable {
    public let index: Int
    public let name: String?
    public let description: String?
    public let inputSchema: JSONValue?
    public let descriptionChars: Int
    public let schemaChars: Int
    public var id: Int { index }
}

public struct ResponseBlock: Codable, Identifiable {
    public let index: Int
    public let type: String?
    public let chars: Int
    public let text: String
    public let available: Bool?
    public var id: Int { index }
}

public struct BreakdownTotals: Codable {
    public let systemChars: Int
    public let messageChars: Int
    public let toolDescriptionChars: Int
    public let toolSchemaChars: Int
}
