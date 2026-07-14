import XCTest
@testable import ContextLensCore

final class BreakdownDecodeTests: XCTestCase {
    private func breakdown(_ name: String = "breakdown") throws -> Breakdown {
        let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures")!
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

    func testDecodesCodexBreakdown() throws {
        let bd = try breakdown("codex-breakdown")
        // five layers decode from a Codex call
        XCTAssertFalse(bd.system.isEmpty)          // base_instructions + developer
        XCTAssertFalse(bd.messages.isEmpty)        // user message + tool activity
        XCTAssertTrue(bd.tools.isEmpty)            // no tool schemas in a rollout
        XCTAssertFalse(bd.requestConfig.isEmpty)   // turn_context config
        // tool-call activity surfaces in L3 (name/arguments), not L4
        XCTAssertTrue(bd.messages.contains { $0.type == "tool_call" })
        // reasoning is an unavailable, zero-char placeholder — the encrypted content
        // must not leak into chars (same honest-placeholder shape as Claude thinking)
        let reasoning = try XCTUnwrap((bd.response ?? []).first { $0.type == "reasoning" },
                                      "Codex breakdown must carry a reasoning placeholder")
        XCTAssertEqual(reasoning.available, false)
        XCTAssertEqual(reasoning.chars, 0)
        XCTAssertEqual(reasoning.text, "")
    }
}
