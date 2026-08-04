import Foundation
import OSLog
import Security

/// The APP owns provider API keys; the engine never reads a keychain (#4534).
///
/// Daniel's decision, and the reason is an identity mismatch rather than a
/// storage problem. The app is code-signed and stable across reboots and engine
/// rebuilds. The engine is a Python process whose executable path differs
/// between Dev (a venv interpreter) and Release (an embedded binary) and moves
/// on every rebuild — and **an ACL can only be as stable as the identity it
/// names.** That is why an OpenRouter key written 2026-07-27 became unreadable
/// after a reboot: `security` exited 36 because the item's ACL no longer
/// trusted the CLI-launched engine, and it could not prompt because it has no
/// UI session to prompt in.
///
/// This is the same `SecItem` shape `AuthTokenMiddleware` already uses for
/// session and device tokens — a third service on an established pattern, not
/// a second keychain mechanism.
enum ProviderKeyStore {

    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "ProviderKeys")

    /// App-owned service. Distinct from the engine's legacy
    /// `com.fichero.fichero` so migration is a copy between two named places
    /// rather than an in-place rewrite whose failure mode is losing the key.
    static let service = "app.fichero.fichero.provider-keys"

    /// The engine's historical service. Read-only from here — we migrate OUT
    /// of it and never write to or delete from it.
    static let legacyService = "com.fichero.fichero"

    /// `AfterFirstUnlock`, matching the token store: the app can be relaunched
    /// or resumed before the user unlocks, and a key that cannot be read then
    /// would present as the very "no key" lie this whole change removes.
    /// Computed, not a `static let`: `CFString` is not `Sendable`, so a stored
    /// static is a strict-concurrency error. The Security constant it reads is
    /// an immutable global, so re-reading it per use costs nothing and needs no
    /// `nonisolated(unsafe)` escape hatch.
    private static var accessibility: CFString { kSecAttrAccessibleAfterFirstUnlock }

    // MARK: - Read / write

    private static func query(service: String, provider: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: provider
        ]
    }

    /// The app-owned key for `provider`, or nil if this app does not hold one.
    ///
    /// Deliberately returns nil for BOTH "no item" and "unreadable": the app is
    /// the owner here, so an unreadable app-owned item is a genuine fault
    /// rather than a state to model — and it is logged loudly rather than
    /// swallowed. The three-state distinction that matters lives on the ENGINE
    /// side, where "nobody supplied it" is a normal condition.
    static func key(for provider: String) -> String? {
        var query = query(service: service, provider: provider)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        switch status {
        case errSecSuccess:
            guard let data = item as? Data, let value = String(data: data, encoding: .utf8) else {
                logger.error("Provider key for \(provider, privacy: .public) is not decodable UTF-8")
                return nil
            }
            return value
        case errSecItemNotFound:
            return nil
        default:
            // Never `debug`. A credential the app owns and cannot read is the
            // loudest thing in the system, not the quietest (#4534).
            logger.error(
                "Could not read app-owned provider key for \(provider, privacy: .public): OSStatus \(status)"
            )
            return nil
        }
    }

    /// Store (or replace) the app-owned key for `provider`.
    @discardableResult
    static func store(_ key: String, for provider: String) -> Bool {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let data = trimmed.data(using: .utf8) else { return false }

        let query = query(service: service, provider: provider)
        let existing = SecItemCopyMatching(query as CFDictionary, nil)

        let status: OSStatus
        if existing == errSecSuccess {
            // The update must carry accessibility too, or a re-store silently
            // writes an attribute-less item back — the exact regression
            // AuthTokenMiddleware documents on its own update path.
            status = SecItemUpdate(query as CFDictionary, [
                kSecValueData as String: data,
                kSecAttrAccessible as String: accessibility
            ] as CFDictionary)
        } else {
            var addQuery = query
            addQuery[kSecValueData as String] = data
            addQuery[kSecAttrAccessible as String] = accessibility
            status = SecItemAdd(addQuery as CFDictionary, nil)
        }

        guard status == errSecSuccess else {
            logger.error(
                "Failed to store provider key for \(provider, privacy: .public): OSStatus \(status)"
            )
            return false
        }
        logger.info("Stored app-owned provider key for \(provider, privacy: .public)")
        return true
    }

    @discardableResult
    static func remove(for provider: String) -> Bool {
        let status = SecItemDelete(query(service: service, provider: provider) as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }

    /// Providers this app holds a key for. Used to decide what to push at
    /// connect — the engine is told about exactly what we have, nothing more.
    static func providersWithKeys(candidates: [String]) -> [String] {
        candidates.filter { key(for: $0) != nil }
    }

    /// Providers the app supplies keys for on connect.
    ///
    /// The cloud providers that need a key at all — local ones (ollama,
    /// lmstudio, omlx) have none by definition. Enumerated rather than
    /// discovered because discovery would mean asking the engine, and the
    /// engine asking the app what to ask for is a loop; this list is the
    /// app's own statement of what it may hold.
    static let candidateProviders = [
        "openai", "anthropic", "openrouter", "google", "huggingface",
        "mistral", "groq", "together", "deepseek"
    ]

    // MARK: - Migration off the engine-owned item

    /// Outcome of one migration attempt, so the caller can report the truth
    /// rather than a boolean that means three things.
    enum MigrationOutcome: Equatable {
        /// The app already owns a key; nothing to do and no prompt shown.
        case alreadyOwned
        /// No legacy item existed — a clean first run, not a failure.
        case noLegacyItem
        /// Read from the legacy item and re-stored under app ownership.
        case migrated
        /// The legacy item exists and could not be read (the user denied the
        /// prompt, or the keychain is locked). `status` is the real OSStatus.
        case refused(OSStatus)
        /// Read succeeded but the app-owned write did not.
        case storeFailed
    }

    /// Take ownership of a key the engine wrote, once, without the user
    /// retyping it.
    ///
    /// DOCUMENTED (Access Control Lists): when the calling app is not among an
    /// item's trusted apps "the system prompts the user for confirmation", and
    /// an Always Allow adds the caller to the trusted list. The app has a UI
    /// session, so it can be prompted where the engine could only be refused.
    ///
    /// **The legacy item is never deleted.** Deleting is the only irreversible
    /// step available here and it buys nothing — a stale duplicate is harmless,
    /// a lost credential is not. A later cleanup can remove it once this path
    /// has proven itself on real machines.
    static func migrateFromLegacyIfNeeded(provider: String) -> MigrationOutcome {
        if key(for: provider) != nil {
            return .alreadyOwned
        }

        var legacyQuery = query(service: legacyService, provider: provider)
        legacyQuery[kSecReturnData as String] = true
        legacyQuery[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(legacyQuery as CFDictionary, &item)

        switch status {
        case errSecSuccess:
            guard let data = item as? Data, let value = String(data: data, encoding: .utf8) else {
                logger.error("Legacy provider key for \(provider, privacy: .public) is not decodable UTF-8")
                return .refused(status)
            }
            guard store(value, for: provider) else { return .storeFailed }
            logger.info(
                """
                Migrated provider key for \(provider, privacy: .public) to app ownership; \
                legacy item left in place deliberately
                """
            )
            return .migrated

        case errSecItemNotFound:
            return .noLegacyItem

        default:
            // The engine hit exactly this and reported it as "no key". We do
            // not repeat that: a refusal is its own outcome, carrying the real
            // status, and the UI says the key exists but could not be read.
            logger.warning(
                """
                Legacy provider key for \(provider, privacy: .public) exists but could not be \
                read (OSStatus \(status)) — reporting as unreadable, NOT as absent
                """
            )
            return .refused(status)
        }
    }
}
