import FicheroAPIClient
import Foundation
import XCTest
@testable import Fichero

/// A shared library that will not open says why (#6459): each cause has its own words and what to do.
final class SharedLibraryOpenerFailureTests: XCTestCase {
    func testEachCauseHasItsOwnWords() {
        let revoked = SharedLibraryOpener.failureWords(for: APIError.httpError(statusCode: 401, message: ""), host: "Air")
        XCTAssertTrue(revoked.sentence.contains("Pair this Mac"))
        let slow = SharedLibraryOpener.failureWords(for: URLError(.timedOut), host: "Air")
        XCTAssertTrue(slow.title.contains("slow"))
        let changed = SharedLibraryOpener.failureWords(for: URLError(.serverCertificateUntrusted), host: "Air")
        XCTAssertTrue(changed.title.contains("identity"))
        let off = SharedLibraryOpener.failureWords(for: URLError(.cannotConnectToHost), host: "Air")
        XCTAssertTrue(off.sentence.contains("asleep"))
        XCTAssertEqual(Set([revoked.title, slow.title, changed.title, off.title]).count, 4)
    }
}
