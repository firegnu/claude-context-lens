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
}
