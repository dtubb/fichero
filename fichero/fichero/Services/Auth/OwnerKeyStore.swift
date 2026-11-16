import CryptoKit
import Foundation
import OSLog
import Security

/// The owner's sign-in key, in the Keychain and synchronised through iCloud Keychain (multiuser-always-on).
///
/// A P-256 key stored as a synchronizable generic password, NOT a Secure Enclave key: the Enclave cannot sync, and
/// the person's other devices must answer the same challenge with the same key. `AfterFirstUnlock`, no
/// user-presence prompt, so the owner's own Mac never asks. The Keychain access group is shared by every bundle id
/// (Dev, Alpha, Beta, App Store, iOS) so a build reopens the same person.
nonisolated struct OwnerKeyStore: OwnerKeyProviding {
    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "OwnerKey")
    static let service = "app.fichero.fichero.owner-key"
    static let account = "owner-signing-key"

    /// Test seam: a different service name keeps a test run away from the real key.
    var serviceName: String = OwnerKeyStore.service

    /// The synchronised item, in the shared access group. Needs the `keychain-access-groups` entitlement.
    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: Self.account,
            kSecAttrSynchronizable as String: kCFBooleanTrue as Any
        ]
    }

    /// The this-Mac-only item (#6374): no access group and no iCloud sync, so it needs no entitlement. A build signed
    /// without `keychain-access-groups` (the DMG's Alpha and Beta) gets -34018 on the synchronised item; this keeps
    /// the owner signed in on that Mac instead of failing.
    var localQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: Self.account
        ]
    }

    /// True for the status a build without the keychain entitlement gets.
    static func needsLocalFallback(_ status: OSStatus) -> Bool { status == errSecMissingEntitlement }

    func loadOrCreate() throws -> P256.Signing.PrivateKey {
        if let existing = try load(baseQuery) ?? load(localQuery) { return existing }
        let key = P256.Signing.PrivateKey()
        var add = baseQuery
        add[kSecValueData as String] = key.rawRepresentation
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        var status = SecItemAdd(add as CFDictionary, nil)
        if status == errSecDuplicateItem, let raced = try load(baseQuery) { return raced }  // another device or process won
        if Self.needsLocalFallback(status) {
            Self.logger.warning("No keychain entitlement (OSStatus \(status)): the owner key is kept on this Mac only, not synced")
            add = localQuery
            add[kSecValueData as String] = key.rawRepresentation
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            status = SecItemAdd(add as CFDictionary, nil)
            if status == errSecDuplicateItem, let raced = try load(localQuery) { return raced }
        }
        guard status == errSecSuccess else {
            Self.logger.error("Could not store the owner key: OSStatus \(status)")
            throw KeychainError.status(status)
        }
        return key
    }

    /// nil when nothing is stored there, or when this build may not read that item (-34018): the caller tries the
    /// this-Mac-only item next.
    private func load(_ base: [String: Any]) throws -> P256.Signing.PrivateKey? {
        var query = base
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        switch status {
        case errSecSuccess:
            guard let data = item as? Data else { throw KeychainError.unreadable }
            return try P256.Signing.PrivateKey(rawRepresentation: data)
        case errSecItemNotFound:
            return nil
        case _ where Self.needsLocalFallback(status):
            return nil
        default:
            // A key we own and cannot read is loud: never silently make a second one over it.
            Self.logger.error("Could not read the owner key: OSStatus \(status)")
            throw KeychainError.status(status)
        }
    }

    enum KeychainError: Error, Equatable {
        case status(OSStatus)
        case unreadable
    }
}

/// Remembers which client this app registered with an engine, so a launch signs in without asking.
nonisolated struct UserDefaultsClientIDStore: ClientIDStoring {
    let engineKey: String

    private var key: String { "app.fichero.signin.clientID." + engineKey }
    func clientID() -> String? { UserDefaults.standard.string(forKey: key) }
    func save(clientID: String) { UserDefaults.standard.set(clientID, forKey: key) }
    func forget() { UserDefaults.standard.removeObject(forKey: key) }
}

/// Debug Dev Local only: the launch secret `dev-uds-engine.sh` left as a 0600 file next to the socket.
/// Read once and deleted. Release, Beta and App Store builds never compile this in; they only spawn their own engine.
#if DEBUG
nonisolated enum DevLaunchSecretFile {
    static func readAndDelete(at url: URL) -> String? {
        defer { try? FileManager.default.removeItem(at: url) }
        guard let text = try? String(contentsOf: url, encoding: .ascii) else { return nil }
        let secret = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return secret.isEmpty ? nil : secret
    }
}
#endif
