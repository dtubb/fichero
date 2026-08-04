#if canImport(AppKit)
import AppKit
#endif
// `nfcNormalizedLastComponent` lives in the API-client module (String+NFC.swift).
import FicheroAPIClient
import Foundation
import UniformTypeIdentifiers

#if os(macOS)

/// The New Library… save-panel seam, shared by the two callers that can start a
/// library create (#4530).
///
/// Extracted from `LibraryWindow.handleNewLibrary` so the SAME panel
/// configuration and the SAME on-disk naming decision serve both the
/// window-scoped path and the app-scoped File-menu fallback. The fallback
/// exists because every File-menu library command is driven by
/// `focusedSceneValue`, which is nil whenever no `LibraryWindow` is key — with
/// zero windows open, or while Settings / Activity / About is frontmost. A
/// second copy of this logic in the fallback is how the two paths would drift.
///
/// The naming decision is a pure function on purpose: `resolvedLibraryURL`
/// is the part that can be wrong (missing extension, NFD-decomposed name) and
/// it is the part a unit test can reach without a live panel.
enum NewLibraryPanel {

    /// The Create-a-library save panel, configured identically for every caller.
    ///
    /// `allowedContentTypes` names the app's OWN exported library type
    /// (`app.fichero.fichero.library`, declared in Info.plist as conforming to
    /// `com.apple.package` with the `fichero` extension) rather than the
    /// abstract `.package`. `.package` would also accept `.app`, `.rtfd` and
    /// every other bundle on disk, and carries no preferred extension for the
    /// panel to offer.
    static func makeSavePanel() -> NSSavePanel {
        let savePanel = NSSavePanel()
        if let libraryType = UTType.ficheroLibrary {
            savePanel.allowedContentTypes = [libraryType]
        }
        savePanel.canCreateDirectories = true
        savePanel.directoryURL = defaultLibraryDirectory
        savePanel.nameFieldStringValue = "Untitled.fichero"
        savePanel.title = "Create New Library"
        savePanel.message = "Choose where to save your new library."
        savePanel.prompt = "Create"
        return savePanel
    }

    /// Where the Create panel OPENS (#4530). Not a restriction — the user can
    /// still navigate anywhere — but the default must be somewhere the engine
    /// will actually serve, because it is the location most libraries get.
    ///
    /// The engine refuses any library outside `ingest_allowed_roots()`
    /// (fichero-server/src/fichero_server/security/path_security.py:248), and
    /// the refusal is a 403 on every library-scoped request, which the app
    /// currently surfaces only as "Library load failed — leaving unloaded for
    /// retry". A library created in the home folder, `~/Downloads`, or on an
    /// external volume is therefore created successfully and then never works.
    /// `~/Documents` is on that allowed list, so a library made here loads.
    ///
    /// This steers the default AWAY from the failure; it does not prevent it.
    /// The app cannot check the allowlist itself — the engine owns that
    /// decision and exposes no endpoint for it — so a library placed outside
    /// it still fails silently. That gap is real and tracked separately; it
    /// needs an engine-side answer, not a second copy of the rules here.
    static var defaultLibraryDirectory: URL? {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
    }

    /// The URL a library actually gets written to, given whatever the panel
    /// returned: the `.fichero` extension is guaranteed, and the package's own
    /// name is NFC-normalized so we never create a mojibake-variant path on
    /// disk (#3076). The user-chosen parent directory already exists and is
    /// left exactly as it is.
    static func resolvedLibraryURL(for url: URL) -> URL {
        let withExtension = url.pathExtension.lowercased() == "fichero"
            ? url
            : url.appendingPathExtension("fichero")
        return withExtension.nfcNormalizedLastComponent
    }

    /// Tell the user the create failed, and where it was trying to write.
    /// Both create paths call this: a silent log line for a button the user
    /// just pressed is indistinguishable from the app ignoring them.
    static func presentCreateFailure(_ error: Error, at url: URL) {
        let alert = NSAlert()
        alert.messageText = "Couldn’t Create Library"
        alert.informativeText = """
            \(error.localizedDescription)

            Tried to create: \(url.path)
            """
        alert.alertStyle = .warning
        alert.runModal()
    }
}

extension UTType {
    /// The app's exported library package type. Resolved from the identifier
    /// declared in Info.plist (`UTExportedTypeDeclarations`) rather than
    /// re-spelling the extension here, so the panel and the declaration cannot
    /// disagree. `nil` only if the declaration is missing, in which case the
    /// caller leaves `allowedContentTypes` unset rather than silently
    /// substituting a broader type.
    static let ficheroLibrary = UTType("app.fichero.fichero.library")
}

#endif
