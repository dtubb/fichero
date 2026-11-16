//
//  CloudRefusedBodyTests.swift
//  FicheroTests
//
//  The 400 of POST /execute is declared as ErrorDetail (a sentence or an object), so the app reads the cloud refusal
//  out of the object itself (ai.cloud.hand-run-refused-before-it-starts, #5094).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct CloudRefusedBodyTests {
    private func decode(_ json: String) throws -> CloudRefusedBody {
        try JSONDecoder().decode(CloudRefusedBody.self, from: Data(json.utf8))
    }

    @Test func anObjectDetailCarriesTheMessageAndTheTypedRefusal() throws {
        let body = try decode("""
        {"detail": {"message": "Over the project cap",
                    "refusal": {"kind": "cap", "scope": "project", "words": "Over the project cap", "fixes": []}}}
        """)
        #expect(body.detail?.message == "Over the project cap")
        #expect(body.detail?.refusal?.scope == .project)
    }

    @Test func aSentenceDetailLeavesNoRefusalAndDoesNotThrow() throws {
        let body = try decode(#"{"detail": "Workflow validation failed: X"}"#)
        #expect(body.detail == nil)
    }
}
