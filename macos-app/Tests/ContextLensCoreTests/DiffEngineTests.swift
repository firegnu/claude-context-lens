import XCTest
@testable import ContextLensCore

final class DiffEngineTests: XCTestCase {
    func testSystemBlockChangedDetectedByPosition() {
        let a = [DiffBlock(identity: "system[0]", content: "old reminder", label: "system[0]", chars: 12)]
        let b = [DiffBlock(identity: "system[0]", content: "new reminder", label: "system[0]", chars: 12)]
        let r = DiffEngine.diffLayer(a, b, layer: .system, matchByIdentity: true)
        XCTAssertEqual(r.changed.count, 1)
        XCTAssertEqual(r.added.count, 0)
        XCTAssertEqual(r.removed.count, 0)
    }

    func testMessagesAppendedShowAsAdded() {
        let a = [DiffBlock(identity: "hi", content: "hi", label: "user", chars: 2)]
        let b = [DiffBlock(identity: "hi", content: "hi", label: "user", chars: 2),
                 DiffBlock(identity: "thanks", content: "thanks", label: "user", chars: 6)]
        let r = DiffEngine.diffLayer(a, b, layer: .messages, matchByIdentity: false)
        XCTAssertEqual(r.added.map(\.content), ["thanks"])
        XCTAssertEqual(r.unchangedCount, 1)
        XCTAssertEqual(r.changed.count, 0)
    }

    func testTopLevelDiffProducesLayersAndSummary() {
        let bd = try! loadFixtureBreakdown()
        let d = DiffEngine.diff(bd, bd)   // identical → no change
        XCTAssertEqual(d.layers.count, DiffLayer.allCases.count)
        XCTAssertFalse(d.layers.contains { $0.hasChange })
        XCTAssertEqual(d.summary.addedBlocks, 0)
        // each layer result carries its own layer id
        XCTAssertEqual(Set(d.layers.map(\.layer.rawValue)),
                       Set(DiffLayer.allCases.map(\.rawValue)))
    }

    func testTextDiffMarksInsertAndDelete() {
        let lines = DiffEngine.textDiff("a\nb\nc", "a\nx\nc")
        XCTAssertTrue(lines.contains(TextDiffLine(kind: .delete, text: "b")))
        XCTAssertTrue(lines.contains(TextDiffLine(kind: .insert, text: "x")))
        XCTAssertTrue(lines.contains(TextDiffLine(kind: .equal, text: "a")))
    }

    private func loadFixtureBreakdown() throws -> Breakdown {
        let url = Bundle.module.url(forResource: "breakdown", withExtension: "json", subdirectory: "Fixtures")!
        return try JSONDecoder.contract.decode(Breakdown.self, from: Data(contentsOf: url))
    }
}
