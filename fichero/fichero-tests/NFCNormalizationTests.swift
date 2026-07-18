//
//  NFCNormalizationTests.swift
//  FicheroTests
//
//  Swift-side NFC normalization (#3076 / #2385). Covers the string/URL helper
//  and the idempotent UserDefaults migration that re-keys legacy NFD path
//  strings to NFC so the app can never create or address a mojibake duplicate.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@Suite("NFC normalization (#3076)")
@MainActor
struct NFCNormalizationTests {

    // Shared sample: "Chocó" in the two Unicode forms.
    private let nfd = "Chocó".decomposedStringWithCanonicalMapping
    private let nfc = "Chocó".precomposedStringWithCanonicalMapping

    // MARK: - String / URL helpers

    @Test("nfcNormalized turns NFD into NFC bytes and is idempotent")
    func stringHelperNormalizes() {
        #expect(nfd != nfc, "sample must actually differ by normalization")
        #expect(nfd.nfcNormalized == nfc)
        #expect(nfc.nfcNormalized == nfc)                 // idempotent
        #expect(nfd.nfcNormalized.nfcNormalized == nfc)   // twice == once
        #expect("plain-ascii".nfcNormalized == "plain-ascii")
    }

    @Test("nfcNormalizedLastComponent normalizes only the leaf")
    func urlHelperNormalizesLeaf() {
        // Parent dir left as-is; only the new package name is canonicalized.
        let url = URL(fileURLWithPath: "/Users/x/Documents/\(nfd).fichero")
        let normalized = url.nfcNormalizedLastComponent
        #expect(normalized.lastPathComponent == "\(nfc).fichero")
        #expect(normalized.deletingLastPathComponent() == url.deletingLastPathComponent())
    }

    // MARK: - UserDefaults migration

    /// Fresh, isolated defaults suite per test.
    private func makeSuite(_ name: String) -> UserDefaults {
        let suite = UserDefaults(suiteName: name)!
        suite.removePersistentDomain(forName: name)
        return suite
    }

    @Test("migration re-keys NFD paths/names to NFC without dropping anything")
    func migrationRekeysToNFC() {
        let name = "nfc-test-basic"
        let suite = makeSuite(name)
        defer { suite.removePersistentDomain(forName: name) }

        let nfdPath = "/Users/x/\(nfd).fichero"
        let nfcPath = "/Users/x/\(nfc).fichero"
        suite.set([nfdPath], forKey: LibraryManager.openLibraryPathsKey)
        suite.set([nfdPath: "My Library"], forKey: LibraryManager.libraryDisplayNamesByPathKey)

        LibraryManager.migrateStoredPathsToNFC(defaults: suite)

        #expect(suite.stringArray(forKey: LibraryManager.openLibraryPathsKey) == [nfcPath])
        let names = suite.dictionary(forKey: LibraryManager.libraryDisplayNamesByPathKey) as? [String: String]
        #expect(names?.count == 1)
        #expect(names?[nfcPath] == "My Library")   // value preserved, re-keyed
    }

    @Test("migration is a no-op the second time")
    func migrationIsIdempotent() {
        let name = "nfc-test-idempotent"
        let suite = makeSuite(name)
        defer { suite.removePersistentDomain(forName: name) }

        suite.set(["/Users/x/\(nfd).fichero"], forKey: LibraryManager.openLibraryPathsKey)
        suite.set(["/Users/x/\(nfd).fichero": "L"], forKey: LibraryManager.libraryDisplayNamesByPathKey)

        LibraryManager.migrateStoredPathsToNFC(defaults: suite)
        let pathsAfterFirst = suite.stringArray(forKey: LibraryManager.openLibraryPathsKey)
        let namesAfterFirst = suite.dictionary(forKey: LibraryManager.libraryDisplayNamesByPathKey) as? [String: String]

        LibraryManager.migrateStoredPathsToNFC(defaults: suite)
        #expect(suite.stringArray(forKey: LibraryManager.openLibraryPathsKey) == pathsAfterFirst)
        #expect((suite.dictionary(forKey: LibraryManager.libraryDisplayNamesByPathKey) as? [String: String]) == namesAfterFirst)
    }

    @Test("colliding NFD+NFC keys collapse to the NFC entry, preferring NFC's value")
    func migrationMergePrefersNFC() {
        let name = "nfc-test-collision"
        let suite = makeSuite(name)
        defer { suite.removePersistentDomain(forName: name) }

        let nfdPath = "/Users/x/\(nfd).fichero"
        let nfcPath = "/Users/x/\(nfc).fichero"
        // Both variants present (array de-dups; dict merges preferring NFC).
        suite.set([nfdPath, nfcPath], forKey: LibraryManager.openLibraryPathsKey)
        suite.set([nfdPath: "old", nfcPath: "new"], forKey: LibraryManager.libraryDisplayNamesByPathKey)

        LibraryManager.migrateStoredPathsToNFC(defaults: suite)

        #expect(suite.stringArray(forKey: LibraryManager.openLibraryPathsKey) == [nfcPath])
        let names = suite.dictionary(forKey: LibraryManager.libraryDisplayNamesByPathKey) as? [String: String]
        #expect(names?.count == 1)
        #expect(names?[nfcPath] == "new")   // NFC entry's value wins
    }

    @Test("distinct libraries are all retained through migration")
    func migrationKeepsDistinctLibraries() {
        let name = "nfc-test-distinct"
        let suite = makeSuite(name)
        defer { suite.removePersistentDomain(forName: name) }

        let nfdPath = "/Users/x/\(nfd).fichero"
        let asciiPath = "/Users/x/Plain.fichero"
        suite.set([nfdPath, asciiPath], forKey: LibraryManager.openLibraryPathsKey)

        LibraryManager.migrateStoredPathsToNFC(defaults: suite)

        let paths = suite.stringArray(forKey: LibraryManager.openLibraryPathsKey) ?? []
        #expect(paths.count == 2)
        #expect(paths.contains("/Users/x/\(nfc).fichero"))
        #expect(paths.contains(asciiPath))
    }
}
