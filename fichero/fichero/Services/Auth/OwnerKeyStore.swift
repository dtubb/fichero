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

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: Self.account,
            kSecAttrSynchronizable as String: kCFBooleanTrue as Any
        ]
    }

    func loadOrCreate() throws -> P256.Signing.PrivateKey {
        if let existing = try load() { return existing }
        let key = P256.Signing.PrivateKey()
        var add = baseQuery
        add[kSecValueData as String] = key.rawRepresentation
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        let status = SecItemAdd(add as CFDictionary, nil)
        if status == errSecDuplicateItem, let raced = try load() { return raced }  // another device or process won
        guard status == errSecSuccess else {
            Self.logger.error("Could not store the owner key: OSStatus \(status)")
            throw KeychainError.status(status)
        }
        return key
    }

    private func load() throws -> P256.Signing.PrivateKey? {
        var query = baseQuery
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
