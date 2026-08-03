import Foundation
import UniformTypeIdentifiers

// MARK: - Reading an in-app drop's payload from its providers (#4474)
//
// `SidebarDropClassification.swift` is the pure DECISION and stays pure. This
// file is the one piece of NSItemProvider plumbing that feeds it, extracted so
// that every surface accepting an in-app item drag reads the drop the same way.
//
// It exists because the plumbing was inline in `SidebarItemRow.handleRowDrop`,
// so the library folder cell could not reuse it without copying it — and a
// copied classifier is precisely how the library section header ended up with a
// second, divergent routing rule (#4401).

/// `@MainActor`: `NSItemProvider` is not Sendable and every caller is a view
/// (the same rule `ExternalFileDropLoader` states).
///
/// Snapshot the providers' capabilities. Cheap, synchronous, and safe to call
/// on the main actor before deciding whether to accept the drop at all.
@MainActor
func sidebarDropCapabilities(of providers: [NSItemProvider]) -> [SidebarDropProviderCapabilities] {
    providers.map {
        SidebarDropProviderCapabilities(
            canLoadURL: $0.canLoadObject(ofClass: URL.self),
            canLoadString: $0.canLoadObject(ofClass: NSString.self),
            registeredTypeIdentifiers: $0.registeredTypeIdentifiers
        )
    }
}

/// Read the drop, then classify it — in that order, which is the #4401 fix.
///
/// Every provider is asked for a string, INCLUDING ones that can also vend a
/// file URL: since #4123 an internal document drag advertises both, so deciding
/// the route from capabilities alone re-imports internal moves.
///
/// Returns `doc:`-prefixed ids for both in-app drag shapes — a sidebar row's
/// `SidebarDragID` and a library row/tile/cell's `LibraryItemDrag` JSON — so a
/// destination never has to know which pane the drag started in. That is the
/// "one payload type for one concept" the #4474 brief asks for, resolved on the
/// reading side where it is safe: the drag SOURCES are deliberately unchanged,
/// because changing a source to satisfy one destination is how #4123 caused
/// #4401, and chat still reads the first string representation (#4401/#4123).
@MainActor
func readSidebarDropPayload(_ providers: [NSItemProvider]) async -> SidebarDropPayload {
    let capabilities = sidebarDropCapabilities(of: providers)
    let hasFileURL = capabilities.contains(where: \.canLoadURL)
    let mightBeInternal = sidebarDropMightCarryInternalID(capabilities)

    var loadedIDs: [String] = []
    for provider in providers where provider.canLoadObject(ofClass: NSString.self) {
        if let string = try? await sidebarDropLoadString(from: provider) {
            loadedIDs.append(string)
        }
    }
    return classifySidebarDropPayload(
        loadedIDs: loadedIDs,
        hasFileURL: hasFileURL,
        carriesOwnProcessFlavor: mightBeInternal
    )
}

/// Unwrap a plain-text `NSItemProvider` into a String.
@MainActor
func sidebarDropLoadString(from provider: NSItemProvider) async throws -> String {
    try await withCheckedThrowingContinuation { continuation in
        _ = provider.loadObject(ofClass: NSString.self) { value, error in
            if let error {
                continuation.resume(throwing: error)
            } else if let nsString = value as? NSString {
                continuation.resume(returning: nsString as String)
            } else {
                continuation.resume(throwing: NSError(domain: "SidebarRowDrop", code: -1))
            }
        }
    }
}
