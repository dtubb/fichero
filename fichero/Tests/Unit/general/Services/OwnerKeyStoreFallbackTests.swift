@testable import Fichero
import Foundation
import Security
import XCTest

/// A build with no keychain entitlement keeps the owner key on this Mac instead of failing sign-in (#6374).
final class OwnerKeyStoreFallbackTests: XCTestCase {
    func testMissingEntitlementStatusTriggersTheFallback() {
        XCTAssertTrue(OwnerKeyStore.needsLocalFallback(-34018))
        XCTAssertFalse(OwnerKeyStore.needsLocalFallback(errSecItemNotFound))
        XCTAssertFalse(OwnerKeyStore.needsLocalFallback(errSecDuplicateItem))
    }

    func testTheLocalItemIsNotSynchronisedAndNeedsNoGroup() {
        let query = OwnerKeyStore().localQuery
        XCTAssertNil(query[kSecAttrSynchronizable as String])
        XCTAssertNil(query[kSecAttrAccessGroup as String])
        XCTAssertEqual(query[kSecAttrAccount as String] as? String, OwnerKeyStore.account)
    }
}
