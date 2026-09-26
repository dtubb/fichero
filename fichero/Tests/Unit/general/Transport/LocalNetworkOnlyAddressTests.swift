import Foundation
import XCTest

@testable import Fichero

/// #5042: the Share sheet used to advertise a `.local` address without saying that
/// it only resolves on the same local network. These pin the predicate that drives
/// the advisory, and that the automatic address has exactly one definition.
@MainActor
final class LocalNetworkOnlyAddressTests: XCTestCase {
    func testMDNSHostIsLocalNetworkOnly() {
        XCTAssertTrue(RemoteAccessConfig.isLocalNetworkOnly("https://studio.local:8765"))
        XCTAssertTrue(RemoteAccessConfig.isLocalNetworkOnly("https://STUDIO.LOCAL:8765"))
        // Leading/trailing whitespace is what a pasted override actually contains.
        XCTAssertTrue(RemoteAccessConfig.isLocalNetworkOnly("  https://studio.local:8765  "))
    }

    func testTailscaleHostIsNotLocalNetworkOnly() {
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly("https://studio.tail1234.ts.net:8765"))
    }

    func testIPLiteralIsNotLocalNetworkOnly() {
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly("https://192.168.1.42:8765"))
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly("https://[fd7a::1]:8765"))
    }

    /// The suffix test must not fire on a routable name that merely CONTAINS
    /// "local" — `local.example.com` resolves through ordinary DNS.
    func testLookalikeDomainIsNotLocalNetworkOnly() {
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly("https://local.example.com:8765"))
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly("https://mylocal:8765"))
    }

    /// A guard that cannot read its input must not pass vacuously in the *unsafe*
    /// direction. Here "not local-only" is the permissive answer, so unparseable
    /// input returning false is only acceptable because it cannot be advertised at
    /// all — `validatedHostedRemoteURL` rejects it first.
    func testUnusableInputIsNotClaimedLocalOnly() {
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly(""))
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly("   "))
        XCTAssertFalse(RemoteAccessConfig.isLocalNetworkOnly("https://"))
        XCTAssertThrowsError(try validatedHostedRemoteURL(from: "https://"))
    }

    func testAutomaticAddressIsDerivedOnceAndIsLocalNetworkOnly() {
        let shared = RemoteAccessConfig.autoLocalBaseURL
        XCTAssertEqual(ShareLibrarySheet.autoLocalBaseURL, shared)
        #if canImport(AppKit)
        XCTAssertEqual(ShareSettingsView.autoLocalBaseURL, shared)
        #endif

        // The automatic address is always an mDNS name, so the Share sheet must
        // always have something honest to say about it.
        XCTAssertTrue(shared.hasPrefix("https://"))
        XCTAssertTrue(RemoteAccessConfig.isLocalNetworkOnly(shared))
        XCTAssertEqual(URLComponents(string: shared)?.host?.hasSuffix(".local"), true)
    }
}
