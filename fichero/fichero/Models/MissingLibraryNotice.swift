import Foundation
import Observation
import SwiftUI

/// A library the app remembered but could not find on launch (`image.ops.missing-library-says-so`, #6384): one alert that names it,
/// with Locate and Remove, instead of a line in the log. The saved path is already dropped from the open list (so it does not
/// fail on every launch); Locate opens the library from where the person chooses, and Remove leaves it dropped. One at a time.
@MainActor
@Observable
final class MissingLibraryNotice {
    static let shared = MissingLibraryNotice()

    /// The paths not yet answered, oldest first.
    private(set) var paths: [String] = []

    /// The path the alert is about.
    var current: String? { paths.first }

    /// True while the panel is up, so the alert is not drawn again behind it.
    private(set) var isLocating = false

    /// Whether the alert shows.
    var isShowing: Bool { current != nil && !isLocating }

    /// The name the alert shows: the package without its extension.
    var currentName: String {
        current.map { URL(fileURLWithPath: $0).deletingPathExtension().lastPathComponent } ?? ""
    }

    func report(_ path: String) {
        if !paths.contains(path) { paths.append(path) }
    }

    /// Remove: the library stays out of the open list; the alert moves on to the next.
    func remove() {
        guard !paths.isEmpty else { return }
        paths.removeFirst()
    }

    /// Locate: open the library from the package the person chose, then move on.
    func located(at url: URL) {
        _ = LibraryManager.shared.openLibrary(at: url)
        remove()
    }
}

#if os(macOS)
extension MissingLibraryNotice {
    /// Locate…: the panel at the missing library's folder, the ordered grant, then the library opens from where it was found.
    func locate() async {
        guard let path = current else { return }
        isLocating = true
        defer { isLocating = false }
        let request = LibraryAccessGrant.Request(missingLibraryURL: URL(fileURLWithPath: path))
        guard let chosen = await FolderAccessManager.shared.chooseForAccess(request) else { return }
        try? await FolderAccessManager.shared.saveBookmarkIfDirectory(chosen)
        located(at: chosen)
    }
}
#endif

extension View {
    /// The alert for `MissingLibraryNotice`: the buttons answer it, so a dismissal is not an answer (Locate… opens a panel first).
    func missingLibraryAlert() -> some View {
        alert(
            "Library Not Found",
            isPresented: Binding(get: { MissingLibraryNotice.shared.isShowing }, set: { _ in })
        ) {
            #if os(macOS)
            Button("Locate\u{2026}") { Task { await MissingLibraryNotice.shared.locate() } }
            #endif
            Button("Remove", role: .cancel) { MissingLibraryNotice.shared.remove() }
        } message: {
            Text(
                "\u{201C}\(MissingLibraryNotice.shared.currentName)\u{201D} is not where Fichero last saw it. "
                    + "Locate it, or remove it from your libraries."
            )
        }
    }
}
