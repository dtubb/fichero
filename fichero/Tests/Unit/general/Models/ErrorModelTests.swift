@testable import Fichero
import XCTest

/// Tests for the `ErrorModel` factory methods. These factories set
/// recovery hints + severity bands that drive the user-visible error
/// dialog — if any factory drifts (wrong severity, missing recovery
/// suggestion), the user gets an inaccurate or unrecoverable-looking
/// dialog for a recoverable error. Locking the shape.
final class ErrorModelTests: XCTestCase {

    // MARK: - Network errors

    func testNetworkErrorDefaults() {
        let err = ErrorModel.networkError(message: "Connection refused")
        XCTAssertEqual(err.type, .network)
        XCTAssertEqual(err.severity, .medium)
        XCTAssertEqual(err.title, "Network Error")
        XCTAssertEqual(err.message, "Connection refused")
        XCTAssertTrue(err.isRecoverable)
        XCTAssertNotNil(err.recoverySuggestion)
    }

    func testNetworkErrorRespectsRecoverableOverride() {
        let err = ErrorModel.networkError(
            message: "fatal", isRecoverable: false
        )
        XCTAssertFalse(err.isRecoverable)
    }

    func testNetworkErrorCarriesContext() {
        let err = ErrorModel.networkError(
            message: "x", context: ["url": "https://example.com"]
        )
        XCTAssertEqual(err.context?["url"], "https://example.com")
    }

    // MARK: - Validation errors

    func testValidationErrorAlwaysRecoverable() {
        let err = ErrorModel.validationError(message: "bad input")
        XCTAssertEqual(err.type, .validation)
        XCTAssertEqual(err.severity, .low)  // low — user can fix
        XCTAssertTrue(err.isRecoverable)
    }

    // MARK: - Permission errors

    func testPermissionErrorNotRecoverable() {
        let err = ErrorModel.permissionError(message: "denied")
        XCTAssertEqual(err.type, .permission)
        XCTAssertEqual(err.severity, .high)
        // Permission errors deliberately not recoverable in-app —
        // user has to fix the OS-level grant.
        XCTAssertFalse(err.isRecoverable)
    }

    // MARK: - File system errors

    func testFileSystemErrorDefaultsRecoverable() {
        let err = ErrorModel.fileSystemError(message: "missing file")
        XCTAssertEqual(err.type, .fileSystem)
        XCTAssertEqual(err.severity, .medium)
        XCTAssertTrue(err.isRecoverable)
    }

    // MARK: - Database errors

    func testDatabaseErrorDefaultsNotRecoverable() {
        let err = ErrorModel.databaseError(message: "corruption")
        XCTAssertEqual(err.type, .database)
        XCTAssertEqual(err.severity, .high)
        XCTAssertFalse(err.isRecoverable)  // restart-the-app path
        XCTAssertEqual(err.recoverySuggestion, "Please restart the application.")
    }

    // MARK: - Direct init

    func testDirectInitFillsDefaults() {
        let err = ErrorModel(
            type: .timeout,
            severity: .critical,
            title: "Timed out",
            message: "no response"
        )
        XCTAssertFalse(err.id.uuidString.isEmpty)
        XCTAssertFalse(err.isRecoverable)  // default
        XCTAssertNil(err.context)
        XCTAssertNil(err.recoverySuggestion)
        XCTAssertNil(err.helpLink)
    }

    // MARK: - Codable

    func testErrorModelEncodes() throws {
        let err = ErrorModel.networkError(message: "test")
        let data = try JSONEncoder().encode(err)
        XCTAssertFalse(data.isEmpty)
    }

    // MARK: - Enum raw values are stable

    func testErrorTypeRawValues() {
        XCTAssertEqual(ErrorType.network.rawValue, "network")
        XCTAssertEqual(ErrorType.notFound.rawValue, "notFound")
        XCTAssertEqual(ErrorType.fileSystem.rawValue, "fileSystem")
    }

    func testSeverityRawValues() {
        XCTAssertEqual(ErrorSeverity.critical.rawValue, "critical")
        XCTAssertEqual(ErrorSeverity.high.rawValue, "high")
        XCTAssertEqual(ErrorSeverity.medium.rawValue, "medium")
        XCTAssertEqual(ErrorSeverity.low.rawValue, "low")
        XCTAssertEqual(ErrorSeverity.info.rawValue, "info")
    }
}
