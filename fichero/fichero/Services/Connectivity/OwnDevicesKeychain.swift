import Foundation
import Security

/// Reads, writes and deletes the own-devices items in iCloud Keychain (`signin.own.*`, #6568): synchronizable generic
/// passwords in the shared access group, `AfterFirstUnlock`, no user-presence prompt, one item per Mac (its engine id is the
/// account). Needs the `keychain-access-groups` entitlement, like `OwnerKeyStore`; a build without it fails loudly.
nonisolated struct OwnDevicesKeychain {
    static let service = "app.fichero.fichero.own-devices"
    /// Test seam: a different service name keeps a test run away from the real items.
    var serviceName: String = OwnDevicesKeychain.service

    enum KeychainError: Error, Equatable { case status(OSStatus) }

    private func query(engineID: String? = nil) -> [String: Any] {
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrSynchronizable as String: kCFBooleanTrue as Any
        ]
        if let engineID { query[kSecAttrAccount as String] = engineID }
        return query
    }

    /// Writes the item, replacing the Mac's earlier one (an address changed, or the secret rotated).
    func write(_ item: OwnDevicesItem) throws {
        let data = try item.encoded()
        let update = SecItemUpdate(query(engineID: item.engineID) as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if update == errSecSuccess { return }
        guard update == errSecItemNotFound else { throw KeychainError.status(update) }
        var add = query(engineID: item.engineID)
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        let status = SecItemAdd(add as CFDictionary, nil)
        guard status == errSecSuccess else { throw KeychainError.status(status) }
    }

    func delete(engineID: String) throws {
        let status = SecItemDelete(query(engineID: engineID) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw KeychainError.status(status) }
    }

    /// Every own-devices item this Apple ID holds; an item that does not decode is skipped (another build's, or damaged).
    func readAll() throws -> [OwnDevicesItem] {
        var search = query()
        search[kSecReturnData as String] = true
        search[kSecMatchLimit as String] = kSecMatchLimitAll
        var found: CFTypeRef?
        let status = SecItemCopyMatching(search as CFDictionary, &found)
        if status == errSecItemNotFound { return [] }
        guard status == errSecSuccess else { throw KeychainError.status(status) }
        return (found as? [Data] ?? []).compactMap { try? OwnDevicesItem.decode($0) }
    }
}
