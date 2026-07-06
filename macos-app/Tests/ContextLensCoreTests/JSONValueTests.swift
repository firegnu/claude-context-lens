import XCTest
@testable import ContextLensCore

final class JSONValueTests: XCTestCase {
    func testDecodesHeterogeneousObject() throws {
        let json = #"{"a": 1, "b": "x", "c": true, "d": null, "e": [1, 2]}"#.data(using: .utf8)!
        let value = try JSONDecoder().decode(JSONValue.self, from: json)
        guard case let .object(dict) = value else { return XCTFail("expected object") }
        XCTAssertEqual(dict["b"], .string("x"))
        XCTAssertEqual(dict["c"], .bool(true))
        XCTAssertEqual(dict["d"], .null)
        XCTAssertEqual(dict["e"], .array([.number(1), .number(2)]))
    }

    func testPrettyStringRendersNestedObject() throws {
        let json = #"{"model":"opus","max_tokens":64000}"#.data(using: .utf8)!
        let value = try JSONDecoder().decode(JSONValue.self, from: json)
        XCTAssertTrue(value.prettyString.contains("\"model\""))
        XCTAssertTrue(value.prettyString.contains("64000"))
    }

    func testLargeWholeNumberRendersWithoutTrapping() throws {
        let json = #"{"big": 9223372036854775807}"#.data(using: .utf8)!
        let value = try JSONDecoder().decode(JSONValue.self, from: json)
        XCTAssertFalse(value.displayString.isEmpty)
        XCTAssertFalse(value.prettyString.isEmpty)
    }

    func testSubscriptAndIntValueReadRawSnakeCaseKeys() throws {
        let json = #"{"input_tokens": 10114, "cache_read_input_tokens": 15298}"#.data(using: .utf8)!
        let value = try JSONDecoder().decode(JSONValue.self, from: json)
        XCTAssertEqual(value["input_tokens"]?.intValue, 10114)
        XCTAssertEqual(value["cache_read_input_tokens"]?.intValue, 15298)
        XCTAssertNil(value["missing"]?.intValue)
    }
}
