/// Cross-platform file-import helper.
///
/// **Why this file?**
/// SwiftUI's `.fileImporter` modifier is available on macOS 11+ and iOS 14+
/// and is fully cross-platform. It is the preferred mechanism for all file
/// picking in Fichero.
///
/// `PlatformFilePicker` wraps `.fileImporter` in a convenience `ViewModifier`
/// so call sites bind a single `Bool` flag and receive a `Result<URL, Error>`
/// callback — identical behaviour on macOS and iOS without any `#if` guards at
/// the call site.
///
/// **macOS NSOpenPanel note**
/// `NSOpenPanel` is NOT used here. `.fileImporter` covers every capability
/// currently needed (single-file, multi-file, UTType filtering). If a future
/// call site genuinely requires an NSOpenPanel-only capability (e.g. choosing
/// a *save* destination with an accessory view), gate that behind
/// `#if os(macOS)` in the relevant feature file; do NOT add it to this shim.
///
/// **Usage**
/// ```swift
/// @State private var isPickerPresented = false
///
/// var body: some View {
///     Button("Import") { isPickerPresented = true }
///         .platformFilePicker(
///             isPresented: $isPickerPresented,
///             allowedContentTypes: [.pdf, .plainText],
///             allowsMultipleSelection: false
///         ) { result in
///             switch result {
///             case .success(let urls): handle(urls)
///             case .failure(let error): log(error)
///             }
///         }
/// }
/// ```

import SwiftUI
import UniformTypeIdentifiers

// MARK: - ViewModifier

/// A `ViewModifier` that presents SwiftUI's built-in `.fileImporter` sheet.
/// Prefer `.platformFilePicker(…)` on `View` (see extension below).
struct PlatformFilePickerModifier: ViewModifier {

    @Binding var isPresented: Bool
    let allowedContentTypes: [UTType]
    let allowsMultipleSelection: Bool
    let onCompletion: (Result<[URL], Error>) -> Void

    func body(content: Content) -> some View {
        content
            .fileImporter(
                isPresented: $isPresented,
                allowedContentTypes: allowedContentTypes,
                allowsMultipleSelection: allowsMultipleSelection,
                onCompletion: onCompletion
            )
    }
}

// MARK: - View extension

extension View {

    /// Present a cross-platform file-import sheet using SwiftUI's `.fileImporter`.
    ///
    /// - Parameters:
    ///   - isPresented: Binding that controls sheet presentation.
    ///   - allowedContentTypes: UTTypes the picker accepts.
    ///   - allowsMultipleSelection: Whether the user can pick multiple files.
    ///   - onCompletion: Called with the selected `[URL]` array on success, or
    ///     an error on failure. Security-scoped access for each URL is the
    ///     caller's responsibility (call `url.startAccessingSecurityScopedResource()`).
    func platformFilePicker(
        isPresented: Binding<Bool>,
        allowedContentTypes: [UTType],
        allowsMultipleSelection: Bool = false,
        onCompletion: @escaping (Result<[URL], Error>) -> Void
    ) -> some View {
        modifier(
            PlatformFilePickerModifier(
                isPresented: isPresented,
                allowedContentTypes: allowedContentTypes,
                allowsMultipleSelection: allowsMultipleSelection,
                onCompletion: onCompletion
            )
        )
    }
}
