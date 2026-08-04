import Foundation
import os
import OSLog
import UniformTypeIdentifiers

// MARK: - ONE drag/drop instrument (Daniel's logging mandate, 2026-08-04)
//
// Every drop surface logs through here, category "dragdrop", so one Console
// filter shows the whole story: what ENTERED (payload UTIs, item count),
// what the VALIDATION decided and WHY, and what the PERFORM delivered or
// refused. The anti-pattern this exists to kill: a refusal that logs
// nothing — the library-cell multi-drag died at AppKit validation with an
// empty console, and silence is the one diagnostic that cannot be read.
//
// LEVELS ARE LOAD-BEARING (#4533). Every non-refusal line here was `.info`,
// and macOS does not PERSIST `.info` or `.debug` — they live in a memory ring
// buffer, so `log show` returns nothing for them once the session is over,
// which is exactly when a drop report gets diagnosed. Measured on the live
// build: `log show --info --debug --predicate 'category == "dragdrop"'`
// returned zero rows over a window containing real drops.
//
// So the accepted path was invisible and only refusals survived, which makes
// "refused" and "never arrived" indistinguishable after the fact — and those
// need opposite fixes. Outcomes are now `.notice` (the default level, which
// IS persisted); refusals stay `.error`. Nothing here may go back to `.info`.
enum DragDropLog {
    static let logger = Logger(subsystem: "app.fichero.fichero", category: "dragdrop")

    /// Monotonic drop-session number, bumped when a delegate COMMITS a drop
    /// (`LibraryItemDropDelegate.validateDrop`). Every line carries the
    /// current `drop#N`, so a multi-surface sequence in one report is
    /// provably one drop or two — live report 2026-08-04: one header drop
    /// logged under two surface names ("sidebar-library-header" then
    /// "sidebar-section-header") and read as two performs. Lock-guarded
    /// rather than actor-isolated because the delegate callbacks and the
    /// MainActor readers must both stamp lines without an await.
    private static let dropSession = OSAllocatedUnfairLock(initialState: 0)

    /// Start a new drop session; returns its number for the caller's own line.
    static func beginDropSession() -> Int {
        dropSession.withLock { session in
            session += 1
            return session
        }
    }

    private static var dropTag: String {
        "drop#\(dropSession.withLock { $0 })"
    }

    /// A drag session reached a surface: name it and dump the payload shape.
    static func entered(_ surface: String, providers: [NSItemProvider]) {
        for (index, provider) in providers.enumerated() {
            let utis = provider.registeredTypeIdentifiers.joined(separator: ", ")
            logger.notice(
                "\(surface): drag entered — provider[\(index)/\(providers.count)] UTIs [\(utis)] [\(dropTag)]"
            )
        }
        if providers.isEmpty {
            logger.notice("\(surface): drag entered with ZERO providers [\(dropTag)]")
        }
    }

    /// A validation verdict, with the reason — especially the refusals.
    static func validated(_ surface: String, accepted: Bool, reason: String) {
        if accepted {
            logger.notice("\(surface): validate ACCEPTED — \(reason) [\(dropTag)]")
        } else {
            logger.error("\(surface): validate REFUSED — \(reason) [\(dropTag)]")
        }
    }

    /// What the drop actually did — target, operation, per-item outcome.
    static func performed(_ surface: String, outcome: String) {
        logger.notice("\(surface): perform — \(outcome) [\(dropTag)]")
    }

    /// A perform-stage refusal, with the precise reason.
    static func refused(_ surface: String, reason: String) {
        logger.error("\(surface): REFUSED — \(reason) [\(dropTag)]")
    }
}

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
/// The load ladder per provider, most-authoritative first:
///  1. `UTType.ficheroDragItem` — THE in-app flavor both drag types export
///     (#4401 multi-drag). Loaded by identifier via the data-representation
///     API, so it survives multi-item sessions that drop proxy flavors.
///  2. A plain-text registration — the single-drag id proxy and legacy shape.
/// A provider carrying neither is judged by `registersExternalPayload` —
/// registration conformance to `public.item`/`public.url` — NOT by
/// `canLoadObject(URL.self)`, which a Finder FOLDER answers false to
/// (live-repro 2026-08-04: `[public.folder] URL:false String:false`).
///
/// Returns `doc:`-prefixed ids for both in-app drag shapes — a sidebar row's
/// `SidebarDragID` and a library row/tile/cell's `LibraryItemDrag` JSON — so a
/// destination never has to know which pane the drag started in.
///
/// `surface` labels the DragDropLog trail: every read logs what arrived and
/// what was decided, so a refused drop can never be silent again.
@MainActor
func readSidebarDropPayload(
    _ providers: [NSItemProvider],
    surface: String = "unlabelled"
) async -> SidebarDropPayload {
    DragDropLog.entered(surface, providers: providers)
    let capabilities = sidebarDropCapabilities(of: providers)
    let hasExternalPayload = capabilities.contains(where: \.registersExternalPayload)
    let mightBeInternal = sidebarDropMightCarryInternalID(capabilities)

    var loadedIDs: [String] = []
    for (index, provider) in providers.enumerated() {
        if provider.hasItemConformingToTypeIdentifier(UTType.ficheroDragItem.identifier) {
            if let payload = try? await sidebarDropLoadFicheroItem(from: provider) {
                loadedIDs.append(payload)
                continue
            }
            DragDropLog.refused(surface, reason: "a fichero-drag-item flavor failed to load its data")
        }
        if provider.canLoadObject(ofClass: NSString.self),
           let string = try? await sidebarDropLoadString(from: provider) {
            loadedIDs.append(string)
            continue
        }
        // Bare public.data with no other identifier is our own drag flavor
        // after the pasteboard degraded its (then-undeclared) custom UTI
        // (live-repro 2026-08-04: an in-app .tif drag arrived as
        // `[public.data] URL:false String:false` and was re-imported as a
        // hollow duplicate). The BYTES survive the degradation, so read them
        // as the envelope and let the classifier judge — recovering the MOVE
        // on builds whose pasteboard still carries the degraded shape.
        if capabilities[index].isUnidentifiedBareData,
           let data = try? await sidebarDropLoadData(
               from: provider, typeIdentifier: UTType.data.identifier
           ),
           let string = String(data: data, encoding: .utf8), !string.isEmpty {
            DragDropLog.performed(
                surface,
                outcome: "bare public.data provider[\(index)] yielded "
                    + "\(data.count) byte(s) of UTF-8 — treating as a degraded in-app envelope"
            )
            loadedIDs.append(string)
        }
    }
    let payload = classifySidebarDropPayload(
        loadedIDs: loadedIDs,
        hasExternalPayload: hasExternalPayload,
        carriesOwnProcessFlavor: mightBeInternal
    )
    DragDropLog.performed(
        surface,
        outcome: "classified \(providers.count) provider(s) as \(String(describing: payload)) "
            + "(internalFlavor: \(mightBeInternal), externalPayload: \(hasExternalPayload), "
            + "loaded \(loadedIDs.count) candidate string(s))"
    )
    return payload
}

/// Load the named in-app flavor's bytes as a UTF-8 string — the id for a
/// `SidebarDragID`, the JSON for a `LibraryItemDrag`; the classifier already
/// speaks both.
@MainActor
func sidebarDropLoadFicheroItem(from provider: NSItemProvider) async throws -> String {
    try await withCheckedThrowingContinuation { continuation in
        _ = provider.loadDataRepresentation(
            forTypeIdentifier: UTType.ficheroDragItem.identifier
        ) { data, error in
            if let data, let string = String(data: data, encoding: .utf8), !string.isEmpty {
                continuation.resume(returning: string)
            } else {
                continuation.resume(throwing: error ?? NSError(domain: "SidebarRowDrop", code: -2))
            }
        }
    }
}

/// Load a provider's raw bytes for one type identifier. Used by the
/// degraded-envelope rung above; the named-flavor rung has its own loader
/// because it also enforces the UTF-8/non-empty envelope contract.
@MainActor
func sidebarDropLoadData(
    from provider: NSItemProvider,
    typeIdentifier: String
) async throws -> Data {
    try await withCheckedThrowingContinuation { continuation in
        _ = provider.loadDataRepresentation(forTypeIdentifier: typeIdentifier) { data, error in
            if let data {
                continuation.resume(returning: data)
            } else {
                continuation.resume(throwing: error ?? NSError(domain: "SidebarRowDrop", code: -3))
            }
        }
    }
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
