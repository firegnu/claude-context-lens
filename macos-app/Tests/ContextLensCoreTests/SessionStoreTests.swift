import XCTest
@testable import ContextLensCore

final class SessionStoreTests: XCTestCase {
    private func makeRoot() throws -> URL {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("lens-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }

    private func writeSession(_ root: URL, _ name: String, json: String) throws {
        let dir = root.appendingPathComponent(name)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try json.data(using: .utf8)!.write(to: dir.appendingPathComponent("session.json"))
    }

    private let minimal = """
    {"session_id":"s","captured_at":"t","launcher_argv":["claude"],"model":"m",
     "counts":{"turns":0,"requests":0,"responses":0,"sidechannel":0},
     "turns":[],"sidechannel":[],"ambiguities":[]}
    """

    func testListsNewestFirstAndFlagsCorrupt() throws {
        let root = try makeRoot()
        try writeSession(root, "20260101-000000", json: minimal)
        try writeSession(root, "20260202-000000", json: minimal)
        try writeSession(root, "20260303-000000", json: "{ not json")

        let entries = SessionStore(root: root).listSessions()
        XCTAssertEqual(entries.map(\.id), ["20260303-000000", "20260202-000000", "20260101-000000"])
        XCTAssertNotNil(entries[0].error)          // corrupt
        XCTAssertNil(entries[0].session)
        XCTAssertNotNil(entries[1].session)        // valid
    }
}
