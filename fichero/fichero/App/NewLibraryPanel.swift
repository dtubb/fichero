#if canImport(AppKit)
import AppKit
#endif
// `nfcNormalizedLastComponent` lives in the API-client module (String+NFC.swift).
import FicheroAPIClient
import Foundation
import UniformTypeIdentifiers

#if os(macOS)

/// The synced-location check setup's Where it lives runs on a folder the person chooses
/// (#5482). The save panel that lived here went with the ruling of 2026-10-05: a project is made
/// by setup, Inside Fichero or in a chosen folder (`NewProjectStore`).
enum NewLibraryPanel {

    /// The sync service covering `url`, or nil when none does. A library is a
    /// live database package; sync engines (iCloud, Dropbox, Google Drive,
    /// Box…) upload it mid-write and can corrupt it or duplicate it across
    /// machines. Detection is by the two places macOS puts synced folders —
    /// File Provider roots under `~/Library/CloudStorage/<Provider>-…` and
    /// iCloud Drive under `~/Library/Mobile Documents` — plus the ubiquitous-
    /// item resource flag, which also catches Desktop & Documents in iCloud.
    static func syncServiceCovering(_ url: URL) -> String? {
        let path = url.path
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        if let range = path.range(of: "/Library/CloudStorage/") {
            // Root folder names look like "Dropbox-Personal", "GoogleDrive-…".
            let provider = path[range.upperBound...].prefix(while: { $0 != "/" })
            return provider.split(separator: "-").first.map(String.init) ?? "a cloud service"
        }
        if path.hasPrefix(home + "/Library/Mobile Documents") { return "iCloud Drive" }
        if path.hasPrefix(home + "/Dropbox") { return "Dropbox" }
        if (try? url.resourceValues(forKeys: [.isUbiquitousItemKey]))?
            .isUbiquitousItem == true { return "iCloud Drive" }
        return nil
    }

    /// Warn-and-confirm before creating a library in a synced location.
    /// Returns true when creation should proceed. Not a ban — an informed
    /// "Create Anyway" is allowed; the default button is Choose Elsewhere.
    @MainActor
    static func confirmSyncedLocationIfNeeded(at url: URL) -> Bool {
        // The panel returns the library URL; sync status is a property of the
        // PARENT folder the package will live in.
        guard let service = syncServiceCovering(url.deletingLastPathComponent()) else {
            return true
        }
        let alert = NSAlert()
        alert.messageText = "This Location Syncs with \(service)"
        alert.informativeText = """
            A Fichero library is a live database. Sync services can upload it \
            mid-write, which risks corruption and duplicate copies. A folder \
            that isn’t synced is safer.
            """
        alert.alertStyle = .warning
        alert.addButton(withTitle: "Choose Another Location")
        alert.addButton(withTitle: "Create Anyway")
        return alert.runModal() == .alertSecondButtonReturn
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
