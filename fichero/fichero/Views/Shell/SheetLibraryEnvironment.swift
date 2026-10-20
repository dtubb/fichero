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

/// What the Set Up window gets when the library window presents it as a sheet: the app's state and the project's
/// services. The sheet hangs off the window, above the library tree where `LibraryTreeEnvironment` is applied, so
/// without this Set Up's page thumbnails and the compare window's page picture found no `StorageService` and drew
/// placeholders (review 360). The one modifier the sheet and its test both use.
struct SetUpSheetEnvironment: ViewModifier {
    let appState: AppState
    let library: LibraryManager.LibraryReference?

    func body(content: Content) -> some View {
        content
            .environment(appState)
            .modifier(SheetLibraryEnvironment(library: library))
    }
}
