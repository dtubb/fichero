@testable import Fichero
import Security
import XCTest

/// #4534 — the app owns provider keys; the engine never reads a keychain.
///
/// These exercise the real keychain, under a test-only service so they cannot
/// touch Daniel's live `openrouter` item. That is deliberate: the whole defect
/// was about what `SecItem` actually returns in states nobody had exercised, and
/// a mocked `SecItem` would have agreed with the broken code just as readily as
/// with the fixed one.
final class ProviderKeyStoreTests: XCTestCase {

    /// A provider name no real provider uses, so a leaked item is obvious and
    /// harmless. Unique per run so a crashed earlier run cannot poison this one.
    private var testProvider = ""

    override func setUp() {
        super.setUp()
        testProvider = "fichero-test-provider-\(UUID().uuidString)"
    }

    override func tearDown() {
        ProviderKeyStore.remove(for: testProvider)
        super.tearDown()
    }

    // MARK: - Round trip

    func testStoreThenReadReturnsTheKey() {
        XCTAssertTrue(ProviderKeyStore.store("sk-test-abc", for: testProvider))
        XCTAssertEqual(ProviderKeyStore.key(for: testProvider), "sk-test-abc")
    }

    func testAbsentKeyIsNilRatherThanEmpty() {
        XCTAssertNil(ProviderKeyStore.key(for: testProvider))
    }

    /// Re-store must UPDATE, not fail or duplicate. The connect path re-supplies
    /// on every connect, so this is the common case, not an edge one.
    func testReStoreReplacesTheExistingValue() {
        ProviderKeyStore.store("first", for: testProvider)
        XCTAssertTrue(ProviderKeyStore.store("second", for: testProvider))
        XCTAssertEqual(ProviderKeyStore.key(for: testProvider), "second")
    }

    /// Edge case: an empty or whitespace key must not create an item that then
    /// reads back as a real key. A phantom key is worse than no key — it makes
    /// the engine report FOUND with nothing behind it.
    func testEmptyKeyIsRejectedAndStoresNothing() {
        XCTAssertFalse(ProviderKeyStore.store("", for: testProvider))
        XCTAssertFalse(ProviderKeyStore.store("   \n", for: testProvider))
        XCTAssertNil(ProviderKeyStore.key(for: testProvider))
    }

    func testKeysAreTrimmed() {
        ProviderKeyStore.store("  sk-padded  ", for: testProvider)
        XCTAssertEqual(ProviderKeyStore.key(for: testProvider), "sk-padded")
    }

    /// Undo: removing must actually remove, and removing twice must not fail —
    /// the connect path can race a user deletion.
    func testRemoveIsIdempotent() {
        ProviderKeyStore.store("sk-test", for: testProvider)
        XCTAssertTrue(ProviderKeyStore.remove(for: testProvider))
        XCTAssertNil(ProviderKeyStore.key(for: testProvider))
        XCTAssertTrue(ProviderKeyStore.remove(for: testProvider), "removing an absent key is not a failure")
    }

    func testProvidersWithKeysReportsOnlyTheOnesHeld() {
        ProviderKeyStore.store("sk-test", for: testProvider)
        let held = ProviderKeyStore.providersWithKeys(
            candidates: [testProvider, "fichero-test-absent-provider"]
        )
        XCTAssertEqual(held, [testProvider])
    }

    // MARK: - Migration

    /// A clean first run is not a failure, and must not be reported as one.
    func testNoLegacyItemIsItsOwnOutcome() {
        XCTAssertEqual(
            ProviderKeyStore.migrateFromLegacyIfNeeded(provider: testProvider),
            .noLegacyItem
        )
    }

    /// Migration must be at-most-once: a second connect must not re-prompt.
    func testAlreadyOwnedShortCircuitsBeforeTouchingTheLegacyItem() {
        ProviderKeyStore.store("sk-owned", for: testProvider)
        XCTAssertEqual(
            ProviderKeyStore.migrateFromLegacyIfNeeded(provider: testProvider),
            .alreadyOwned
        )
        XCTAssertEqual(ProviderKeyStore.key(for: testProvider), "sk-owned")
    }

    /// THE migration path, end to end, with a real legacy item planted under the
    /// engine's service name.
    func testLegacyKeyIsAdoptedAndTheLegacyItemSurvives() throws {
        try plantLegacyItem("sk-legacy-value")
        defer { removeLegacyItem() }

        XCTAssertEqual(
            ProviderKeyStore.migrateFromLegacyIfNeeded(provider: testProvider),
            .migrated
        )
        XCTAssertEqual(ProviderKeyStore.key(for: testProvider), "sk-legacy-value")

        // The condition that matters most. Deleting is the only irreversible
        // step available and it buys nothing: a stale duplicate is harmless, a
        // lost credential is not. Daniel must never be asked to retype.
        XCTAssertEqual(try readLegacyItem(), "sk-legacy-value", "the legacy item must be left in place")
    }

    /// Migrating twice is a no-op the second time — it must not re-read the
    /// legacy item, because on a real machine that is what re-prompts the user.
    func testMigrationIsAtMostOnce() throws {
        try plantLegacyItem("sk-legacy-value")
        defer { removeLegacyItem() }

        XCTAssertEqual(ProviderKeyStore.migrateFromLegacyIfNeeded(provider: testProvider), .migrated)
        XCTAssertEqual(ProviderKeyStore.migrateFromLegacyIfNeeded(provider: testProvider), .alreadyOwned)
    }

    /// The outcome type must keep the states separate. A boolean here would be
    /// the same collapse the engine side was fixed to stop making: "refused"
    /// and "nothing to migrate" are opposite facts.
    func testMigrationOutcomesAreDistinct() {
        XCTAssertNotEqual(ProviderKeyStore.MigrationOutcome.noLegacyItem, .refused(errSecAuthFailed))
        XCTAssertNotEqual(ProviderKeyStore.MigrationOutcome.migrated, .alreadyOwned)
        XCTAssertNotEqual(
            ProviderKeyStore.MigrationOutcome.refused(errSecAuthFailed),
            .refused(errSecInteractionNotAllowed),
            "the real OSStatus must survive — it is what the user is told"
        )
    }

    // MARK: - Config

    /// Local providers need no key, so pushing one would be meaningless; and a
    /// candidate list that missed openrouter would silently fail to migrate the
    /// exact key this work exists for.
    func testCandidateProvidersCoverCloudAndExcludeLocal() {
        XCTAssertTrue(ProviderKeyStore.candidateProviders.contains("openrouter"))
        XCTAssertTrue(ProviderKeyStore.candidateProviders.contains("openai"))
        for local in ["ollama", "lmstudio", "omlx"] {
            XCTAssertFalse(
                ProviderKeyStore.candidateProviders.contains(local),
                "\(local) is a local provider and has no API key to supply"
            )
        }
    }

    /// The app-owned service must never be the engine's — migration is a copy
    /// between two named places, and if they were the same string it would be
    /// an in-place rewrite whose failure mode is losing the key.
    func testAppOwnedServiceIsDistinctFromTheLegacyOne() {
        XCTAssertNotEqual(ProviderKeyStore.service, ProviderKeyStore.legacyService)
        XCTAssertEqual(ProviderKeyStore.legacyService, "com.fichero.fichero")
    }

    // MARK: - Legacy-item helpers (test-only, under the test provider name)

    private func legacyQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: ProviderKeyStore.legacyService,
            kSecAttrAccount as String: testProvider
        ]
    }

    private func plantLegacyItem(_ value: String) throws {
        removeLegacyItem()
        var query = legacyQuery()
        query[kSecValueData as String] = Data(value.utf8)
        let status = SecItemAdd(query as CFDictionary, nil)
        try XCTSkipUnless(
            status == errSecSuccess,
            "could not plant a legacy keychain item (OSStatus \(status)) — skipping rather than passing vacuously"
        )
    }

    private func readLegacyItem() throws -> String? {
        var query = legacyQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func removeLegacyItem() {
        SecItemDelete(legacyQuery() as CFDictionary)
    }
}
