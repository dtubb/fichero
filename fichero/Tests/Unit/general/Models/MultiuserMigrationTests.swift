import XCTest

@testable import Fichero

@MainActor
final class MultiuserMigrationTests: XCTestCase {
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        defaults = UserDefaults(suiteName: "MultiuserMigrationTests.\(UUID().uuidString)")
    }

    private let refused = APIError.httpError(
        statusCode: 409, message: "Multi-user needs the owner's account to have a password first")
    private struct Unreachable: Error {}

    func testA401IsNotAnAnswerAndDoesNotSpendTheTry() {
        XCTAssertFalse(MultiuserMigration.engineAnswered(APIError.httpError(statusCode: 401, message: "missing or invalid Authorization header")))
        XCTAssertTrue(MultiuserMigration.engineAnswered(refused))
    }

    func testOnlyAnOldAppOnWithTheEngineOffIsPushed() {
        XCTAssertTrue(MultiuserMigration.shouldPush(localOn: true, engineOn: false, alreadyTried: false, engineIsLocal: true))
        XCTAssertFalse(MultiuserMigration.shouldPush(localOn: false, engineOn: false, alreadyTried: false, engineIsLocal: true))
        XCTAssertFalse(MultiuserMigration.shouldPush(localOn: true, engineOn: true, alreadyTried: false, engineIsLocal: true))
        XCTAssertFalse(MultiuserMigration.shouldPush(localOn: true, engineOn: false, alreadyTried: true, engineIsLocal: true))
        XCTAssertFalse(MultiuserMigration.shouldPush(localOn: true, engineOn: false, alreadyTried: false, engineIsLocal: false))
    }

    func testItTurnsMultiuserOnOnceAndNeverAgain() async {
        defaults.set(true, forKey: EngineConfig.multiuserEnabledKey)
        var calls = 0
        let first = await MultiuserMigration.run(engineOn: false, engineIsLocal: true, defaults: defaults) { calls += 1 }
        let second = await MultiuserMigration.run(engineOn: false, engineIsLocal: true, defaults: defaults) { calls += 1 }
        XCTAssertTrue(first)
        XCTAssertFalse(second)
        XCTAssertEqual(calls, 1)
        XCTAssertNil(MultiuserMigration.takeNote(defaults: defaults))
    }

    func testARefusalIsSaidOnceAndNotRetried() async {
        defaults.set(true, forKey: EngineConfig.multiuserEnabledKey)
        var calls = 0
        _ = await MultiuserMigration.run(engineOn: false, engineIsLocal: true, defaults: defaults) { calls += 1; throw refused }
        _ = await MultiuserMigration.run(engineOn: false, engineIsLocal: true, defaults: defaults) { calls += 1; throw refused }
        XCTAssertEqual(calls, 1, "a refusal does not loop")
        let note = MultiuserMigration.takeNote(defaults: defaults)
        XCTAssertEqual(note?.contains("owner's account to have a password"), true)
        XCTAssertNil(MultiuserMigration.takeNote(defaults: defaults), "said once")
    }

    func testATransportErrorDoesNotSpendTheTry() async {
        defaults.set(true, forKey: EngineConfig.multiuserEnabledKey)
        var calls = 0
        let first = await MultiuserMigration.run(engineOn: false, engineIsLocal: true, defaults: defaults) { calls += 1; throw Unreachable() }
        XCTAssertFalse(first)
        XCTAssertNil(MultiuserMigration.takeNote(defaults: defaults))
        let second = await MultiuserMigration.run(engineOn: false, engineIsLocal: true, defaults: defaults) { calls += 1 }
        XCTAssertTrue(second)
        XCTAssertEqual(calls, 2, "tried again next launch")
    }

    func testTheNoteDoesNotBlameTheEnvironmentUnderDevLocal() {
        let note = MultiuserMigration.note(for: "Multi-user is set by FICHERO_MULTIUSER; unset it to change it here")
        XCTAssertFalse(note.contains("FICHERO_MULTIUSER"))
    }

    func testTheLocalCopyFollowsTheEngine() {
        defaults.set(true, forKey: EngineConfig.multiuserEnabledKey)
        MultiuserMigration.follow(engineOn: false, defaults: defaults)
        XCTAssertFalse(defaults.bool(forKey: EngineConfig.multiuserEnabledKey))
    }
}
