import XCTest
@testable import ContextLensCore

final class SessionDecodeTests: XCTestCase {
    private func fixture(_ name: String) throws -> Data {
        let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures")!
        return try Data(contentsOf: url)
    }

    func testDecodesRealSession() throws {
        let session = try JSONDecoder.contract.decode(Session.self, from: fixture("session"))
        XCTAssertFalse(session.turns.isEmpty)
        XCTAssertEqual(session.counts.turns, session.turns.count)
        // side-channel requests are separated out, never inside turns
        for turn in session.turns {
            XCTAssertTrue(turn.requests.allSatisfy { !$0.isSidechannel })
        }
        // sidechannel entries are all flagged
        XCTAssertTrue(session.sidechannel.allSatisfy { $0.isSidechannel })
        // ambiguities use the unified {kind,file,detail} shape
        for amb in session.ambiguities {
            XCTAssertFalse(amb.kind.isEmpty)
        }
    }

    func testDecodesCodexSession() throws {
        // Codex ingest produces the SAME contract as Claude, but a Codex request
        // has no verbatim wire body (raw_request), and the session carries
        // reconstruction / compaction / multi_agent ambiguity notes. The app must
        // decode a Codex session, not choke on it.
        let session = try JSONDecoder.contract.decode(Session.self, from: fixture("codex-session"))
        XCTAssertFalse(session.turns.isEmpty)
        XCTAssertEqual(session.counts.turns, session.turns.count)
        // the requests decode even with no raw request body (the bug this locks)
        XCTAssertFalse(session.turns.flatMap { $0.requests }.isEmpty)
        // Codex fidelity notes survive into the contract the app reads
        let kinds = Set(session.ambiguities.map(\.kind))
        XCTAssertTrue(kinds.contains("multi_agent"))
        XCTAssertTrue(kinds.contains("compaction"))
    }

    func testCodexSessionCarriesSourceMarker() throws {
        let codex = try JSONDecoder.contract.decode(Session.self, from: fixture("codex-session"))
        XCTAssertEqual(codex.source, "codex")
        // Claude sessions have no source marker -> nil (the app treats absence as Claude)
        let claude = try JSONDecoder.contract.decode(Session.self, from: fixture("session"))
        XCTAssertNil(claude.source)
    }
}
