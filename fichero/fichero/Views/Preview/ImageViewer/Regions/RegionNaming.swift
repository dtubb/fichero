#if os(macOS)
import SwiftUI

// MARK: - Naming a region before it is saved
//
// Daniel, 2026-08-31: "if we draw it, we should be able to save it, and double
// click on it to be taken to a new region. Marquee select can do that — then
// you right-mouse-click to make a new region, or have an icon beside it, which
// lets you give it a name."
//
// The pending name is a small armed REQUEST rather than view state, for the
// same reason `RegionSelection` is one: two affordances over the same picture
// arm it — the pencil badge beside a freshly drawn marquee, and the
// right-click verb — and the name typed under one must be the name the other
// commits.

/// The armed "name this region" request. Per-app rather than per-window
/// because only one naming popover can be open at a time; the `documentId`
/// gate keeps a stale request from re-arming over a different page.
@MainActor
@Observable
final class RegionNamingRequest {
    static let shared = RegionNamingRequest()

    /// The page the pending name belongs to. `nil` = nothing armed.
    private(set) var documentId: String?
    /// Which marquee is being named; `nil` means EVERY drawn marquee (the
    /// right-click verb, which acts on the whole set).
    private(set) var marqueeIndex: Int?
    /// Live text in the field.
    var name: String = ""

    private init() {}

    var isArmed: Bool { documentId != nil }

    func arm(documentId: String, marqueeIndex: Int?) {
        self.documentId = documentId
        self.marqueeIndex = marqueeIndex
        name = ""
    }

    func clear() {
        documentId = nil
        marqueeIndex = nil
        name = ""
    }

    /// True when the popover should hang off marquee `index`'s badge. A
    /// whole-set request anchors on the FIRST badge — there is no other
    /// honest anchor for "all of them", and an unanchored popover would
    /// appear detached from the boxes it is about to save.
    func anchors(documentId: String, index: Int) -> Bool {
        guard self.documentId == documentId else { return false }
        return marqueeIndex == index || (marqueeIndex == nil && index == 0)
    }
}

/// The one-field naming popover: type a name, Enter saves. Cancel (or
/// click-away) leaves the marquee exactly as it was drawn — naming is an
/// invitation, never a toll gate; an empty name saves the region unnamed.
struct RegionNameField: View {
    @Bindable var request: RegionNamingRequest
    /// Commit with the typed name (may be empty).
    let commit: (String) -> Void

    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Name This Region")
                .font(.headline)
            TextField("Region name", text: $request.name)
                .textFieldStyle(.roundedBorder)
                .frame(width: 220)
                .focused($focused)
                .onSubmit { commit(request.name) }
                .help("Give the new region a name. Leave blank to save it unnamed.")
            HStack {
                Button("Cancel", role: .cancel) { request.clear() }
                    .help("Leave the selection as it is, without saving a region")
                Spacer()
                Button("Save Region") { commit(request.name) }
                    .keyboardShortcut(.defaultAction)
                    .help("Save the selection as a region with this name")
            }
        }
        .padding(12)
        .onAppear { focused = true }
    }
}

#endif
