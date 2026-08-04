import Foundation
import UniformTypeIdentifiers
import XCTest

@testable import Fichero

/// Behavioral pins for `ExternalFileDropLoader`'s ladder, with REAL
/// `NSItemProvider`s (live-repro 2026-08-04: a Finder folder drop onto the
/// library header advertised ONLY `[public.folder]`, classification routed it
/// to import, and the read then failed with "Couldn't read the dropped
/// item(s)" — `loadFileRepresentation` is documented as writing "a copy of
/// the provided, typed data to a temporary file", a FLAT file, which a
/// directory cannot be. The documented folder path is
/// `loadInPlaceFileRepresentation` / `loadItem`'s NSURL coercion, which the
/// loader now tries for directory-conforming UTIs).
@MainActor
final class ExternalFileDropLoaderBehaviorTests: XCTestCase {

    private var scratchDirectory: URL!

    override func setUpWithError() throws {
        scratchDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("loader-behavior-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: scratchDirectory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: scratchDirectory)
    }

    private func makeRealFolder(named name: String) throws -> URL {
        let folder = scratchDirectory.appendingPathComponent(name)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try Data("page one".utf8).write(to: folder.appendingPathComponent("page1.txt"))
        return folder
    }

    /// THE live repro shape: a provider registering ONLY `public.folder`,
    /// backed by an open-in-place representation. The loader must yield the
    /// REAL directory URL — the user's own folder, exactly as if it had been
    /// chosen via the import menu — and must NOT stage it into a
    /// `fichero-drop-*` copy.
    func testAFolderOnlyInPlaceProviderYieldsItsRealDirectoryURL() async throws {
        let folder = try makeRealFolder(named: "Box 12")
        let provider = NSItemProvider()
        provider.registerFileRepresentation(
            forTypeIdentifier: UTType.folder.identifier,
            fileOptions: [.openInPlace],
            visibility: .all
        ) { completion in
            completion(folder, false, nil)
            return nil
        }
        XCTAssertEqual(provider.registeredTypeIdentifiers, [UTType.folder.identifier])
        XCTAssertFalse(
            provider.canLoadObject(ofClass: URL.self),
            "platform truth (live console 2026-08-04): a folder-only provider answers false — "
                + "if this flips, the direct-URL rung covers it and this pin is stale"
        )

        let loaded = try await ExternalFileDropLoader.loadAnyFileURL(from: provider)

        XCTAssertEqual(
            loaded.resolvingSymlinksInPath().path,
            folder.resolvingSymlinksInPath().path,
            "an in-place folder must come back as ITSELF, not a copy"
        )
        XCTAssertFalse(loaded.path.contains("/fichero-drop-"))
        var isDirectory: ObjCBool = false
        XCTAssertTrue(FileManager.default.fileExists(atPath: loaded.path, isDirectory: &isDirectory))
        XCTAssertTrue(isDirectory.boolValue)
    }

    /// Second directory rung: some sources vend the folder as an NSURL item
    /// rather than a file representation. `loadItem`'s coercion must return
    /// the real location untouched.
    func testLoadItemURLCoercesAnNSURLBackedFolderProvider() async throws {
        let folder = try makeRealFolder(named: "Carpeta")
        let provider = NSItemProvider(
            item: folder as NSURL,
            typeIdentifier: UTType.folder.identifier
        )

        let loaded = try await ExternalFileDropLoader.loadItemURL(
            from: provider,
            typeIdentifier: UTType.folder.identifier
        )

        XCTAssertEqual(
            loaded.resolvingSymlinksInPath().path,
            folder.resolvingSymlinksInPath().path
        )
    }

    /// Daniel's other live shape (2026-08-04): a Finder PDF drag advertising
    /// ONLY `[com.adobe.pdf]` — no `public.file-url`. This is the designed
    /// `loadFileRepresentation` case: the loader stages the bytes into a
    /// stable `fichero-drop-*` copy that survives the provider's own temp
    /// file being deleted.
    func testAContentUTIOnlyPDFProviderYieldsAReadableFileCopy() async throws {
        let bytes = Data("%PDF-1.4 not really".utf8)
        let provider = NSItemProvider()
        provider.registerDataRepresentation(
            forTypeIdentifier: UTType.pdf.identifier,
            visibility: .all
        ) { completion in
            completion(bytes, nil)
            return nil
        }
        XCTAssertEqual(provider.registeredTypeIdentifiers, [UTType.pdf.identifier])

        let loaded = try await ExternalFileDropLoader.loadAnyFileURL(from: provider)

        XCTAssertTrue(
            loaded.path.contains("/fichero-drop-"),
            "a content-only representation is provider-owned and must be stabilized"
        )
        XCTAssertEqual(try Data(contentsOf: loaded), bytes)
        // The staging directory is discoverable for post-import cleanup.
        XCTAssertEqual(externalDropTemporaryDirectories(for: [loaded]).count, 1)
    }

    /// The never-materialize guard survives the new rungs: a provider whose
    /// only flavor is our own drag envelope must throw, not write the
    /// envelope to disk and hand it to the importer (the "<name>.tif.json"
    /// stray of 2026-08-04).
    func testTheFicheroDragItemFlavorIsNeverMaterialized() async {
        let provider = NSItemProvider()
        provider.registerDataRepresentation(
            forTypeIdentifier: UTType.ficheroDragItem.identifier,
            visibility: .all
        ) { completion in
            completion(Data("{\"kind\":\"document\",\"id\":\"a\"}".utf8), nil)
            return nil
        }
        do {
            let url = try await ExternalFileDropLoader.loadAnyFileURL(from: provider)
            XCTFail("the in-app flavor must never materialize; got \(url.path)")
        } catch {
            // Expected: the ladder skips the flavor and reports nothing readable.
        }
    }
}
