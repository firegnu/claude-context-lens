import XCTest
@testable import ContextLensCore

final class BreakdownDecodeTests: XCTestCase {
    private func breakdown() throws -> Breakdown {
        let url = Bundle.module.url(forResource: "breakdown", withExtension: "json", subdirectory: "Fixtures")!
        return try JSONDecoder.contract.decode(Breakdown.self, from: Data(contentsOf: url))
    }

    func testDecodesLayers() throws {
        let bd = try breakdown()
        XCTAssertFalse(bd.system.isEmpty)
        XCTAssertFalse(bd.messages.isEmpty)
        XCTAssertFalse(bd.tools.isEmpty)
        XCTAssertFalse(bd.requestConfig.isEmpty)
        XCTAssertGreaterThan(bd.totals.systemChars, 0)
    }

    func testThinkingBlockIsMarkedUnavailable() throws {
        let bd = try breakdown()
        let thinking = try XCTUnwrap((bd.response ?? []).first { $0.type == "thinking" },
                                     "fixture must contain a thinking response block")
        XCTAssertEqual(thinking.available, false)
        XCTAssertEqual(thinking.chars, 0)
        XCTAssertEqual(thinking.text, "")
    }
}
