import SwiftUI

/// Platform-adaptive placement for a detachable inspector / detail pane (#2254,
/// reform master plan §E). Generalizes the precedent set by the five detachable
/// `WindowGroup` detail scenes (`ArtifactDetailWindow` & friends, EPIC #2002–#2005)
/// that already observe a shared `@Observable` focus holder (`FocusedArtifact`).
///
/// Three placements:
/// - ``docked``   — the inspector lives in its column (today's behaviour).
/// - ``floating`` — torn off into a separate window that floats above the
///   primary window (macOS) or a secondary scene (iPad with multiple scenes).
///   Reuses the already-registered detail `WindowGroup` scenes — we do **not**
///   add a parallel scene.
/// - ``sheet``    — presented as a sheet with `presentationDetents` (iPhone /
///   any size class with no multi-window support).
///
/// **§7.3 design decision (deferred):** the open question of *one palette vs many
/// pinned* floating inspectors, and *read-only vs editable when floating*, is not
/// resolved here. This ships the simplest answer: a **single docked default**,
/// **floating as an opt-in** affordance, and **read-only when floating** (matching
/// the existing `ArtifactDetailWindow`, which observes a read-only snapshot).
enum InspectorPlacement: String, CaseIterable, Sendable {
    case docked
    case floating
    case sheet
}

extension InspectorPlacement {
    /// The simplest sensible default for the current window's capabilities.
    ///
    /// - Compact width (iPhone, narrow split views) → ``sheet``.
    /// - Otherwise → ``docked`` — the user opts in to ``floating`` via the
    ///   detach affordance.
    ///
    /// Explicit requests are passed through unchanged so existing detach/future
    /// callers can opt into a specific placement.
    static func adaptiveDefault(
        horizontalSizeClass: UserInterfaceSizeClass?,
        requested: InspectorPlacement? = nil
    ) -> InspectorPlacement {
        switch requested {
        case let .some(placement):
            return placement
        case .none:
            return horizontalSizeClass == .compact ? .sheet : .docked
        }
    }
}

/// A reusable toolbar button that tears the current detail off into its floating
/// scene. Gated on `@Environment(\.supportsMultipleWindows)`: the button is
/// **absent** where a second window can't exist (iPhone), so no call site has to
/// guard `openWindow` by hand. This is the single, generalized version of the
/// hand-rolled "Open in Window" buttons the detachable detail panes carried.
struct DetachInspectorButton: View {
    /// Whether a detail is currently selected and therefore detachable.
    var isEnabled: Bool
    /// Opens the matching, already-registered detail `WindowGroup` scene.
    /// The caller is responsible for refreshing the shared focus snapshot first.
    var action: () -> Void

    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows

    var body: some View {
        if supportsMultipleWindows {
            Button(action: action) {
                Label("Open in Window", systemImage: "macwindow.badge.plus")
            }
            .help("Open the selected item in a separate, floating window")
            .disabled(!isEnabled)
        }
    }
}

extension View {
    @ViewBuilder
    func adaptiveInspector<InspectorContent: View>(
        placement: InspectorPlacement,
        isPresented: Binding<Bool>,
        detents: Set<PresentationDetent> = [.medium, .large],
        @ViewBuilder content: @escaping () -> InspectorContent
    ) -> some View {
        #if os(visionOS)
        inspectorSheet(isPresented: isPresented, detents: detents, content: content)
        #else
        switch placement {
        case .sheet:
            inspectorSheet(isPresented: isPresented, detents: detents, content: content)
        case .docked, .floating:
            inspector(isPresented: isPresented, content: content)
        }
        #endif
    }

    /// Presents detail `content` as a detented sheet — the ``InspectorPlacement/sheet``
    /// placement for compact / single-window platforms. A no-op shape-wise on
    /// macOS where the docked column is used instead.
    func inspectorSheet<SheetContent: View>(
        isPresented: Binding<Bool>,
        detents: Set<PresentationDetent> = [.medium, .large],
        @ViewBuilder content: @escaping () -> SheetContent
    ) -> some View {
        sheet(isPresented: isPresented) {
            content()
                .presentationDetents(detents)
                .presentationDragIndicator(.visible)
        }
    }
}

#Preview("Detach button (multi-window)") {
    VStack(spacing: 16) {
        DetachInspectorButton(isEnabled: true) {}
        DetachInspectorButton(isEnabled: false) {}
    }
    .padding()
    .frame(width: 240)
}
