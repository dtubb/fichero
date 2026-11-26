//
//  RememberedOriginalsRootTests.swift
//  FicheroTests
//
//  Locate Originals' folder grant mints a read-write scoped bookmark from the kept folder (#7076), so the
//  kept bookmark must not be read-only scoped.
//

@testable import Fichero
import Foundation
import Testing

struct RememberedOriginalsRootTests {
    @Test func keptBookmarkIsNotReadOnlyScoped() {
        let options = RememberedOriginalsRoot.creationOptions
        #if os(macOS)
        #expect(options.contains(.withSecurityScope))
        #expect(!options.contains(.securityScopeAllowOnlyReadAccess))
        #else
        #expect(options.isEmpty)
        #endif
    }
}
