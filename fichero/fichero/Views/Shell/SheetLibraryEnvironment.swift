import SwiftUI

/// Sheet-boundary variant of `libraryServiceEnvironment`: sheets take an
/// OPTIONAL library reference (a sheet can present while no library is
/// resolved) and must not crash the modifier chain when it is nil — the
/// content then fails on its own read, which the optional-guard work makes
/// survivable for guarded views and diagnosable for the rest.
struct SheetLibraryEnvironment: ViewModifier {
    let library: LibraryManager.LibraryReference?

    func body(content: Content) -> some View {
        if let library {
            content.libraryServiceEnvironment(library)
        } else {
            content
        }
    }
}
