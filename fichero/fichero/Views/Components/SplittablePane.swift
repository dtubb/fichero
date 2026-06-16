import SwiftUI

/// Axis a content pane is split along. `nil` (empty raw) = not split.
/// - `vertical`   → left / right halves (`HSplitView`)
/// - `horizontal` → top / bottom halves (`VSplitView`)
enum PaneSplitAxis: String, CaseIterable, Identifiable {
    case vertical    // left / right  (HSplitView)
    case horizontal  // top / bottom  (VSplitView)

    var id: String { rawValue }
}

/// Wraps a reorganizable content pane — the Library list, the image / canvas
/// viewer, or the WebKit "Knowledge" reading surface — so the user can split it
/// **left/right** or **top/bottom** and view two copies side-by-side, then
/// collapse back to a single view.
///
/// This EXTENDS the existing split infrastructure used across `ContentView`
/// (native `HSplitView` / `VSplitView` + `ResizableDivider`, the widescreen
/// multi-pane layout) to the three reorganizable content panes named in
/// `reform_masterplan_2026-06.md` §6d (#2276). It does not replace any view —
/// it only wraps an existing pane's content in a resizable split.
///
/// Scope (deliberately minimal — see #2276):
/// - The two halves render the **same** content view. Giving each half its own
///   independent navigation / selection state is a larger follow-up and is
///   intentionally **deferred**.
/// - Arbitrary drag-anywhere pane rearrangement is **out of scope**; this ships
///   only the h/v split named in §6d, reusing the native split-view pattern.
///
/// The split axis is remembered per-pane per-window via `@SceneStorage`, so it
/// survives window state restoration (aligning with the reform window-state
/// goal) without any backend round-trip.
struct SplittablePane<Content: View>: View {
    private let storageKey: String
    private let content: () -> Content

    @SceneStorage private var axisRaw: String

    /// - Parameters:
    ///   - storageKey: stable per-pane key (e.g. "library", "canvas", "reading")
    ///     used to persist the split state per window.
    ///   - content: the pane's existing view, rendered once when unsplit and
    ///     twice when split.
    init(storageKey: String, @ViewBuilder content: @escaping () -> Content) {
        self.storageKey = storageKey
        self.content = content
        self._axisRaw = SceneStorage(wrappedValue: "", "splittablePane.\(storageKey)")
    }

    private var axis: PaneSplitAxis? { PaneSplitAxis(rawValue: axisRaw) }

    var body: some View {
        splitContainer
            .overlay(alignment: .topTrailing) { splitControls }
    }

    @ViewBuilder
    private var splitContainer: some View {
        switch axis {
        case .vertical:
            HSplitView {
                content()
                    .frame(minWidth: 240, maxWidth: .infinity, maxHeight: .infinity)
                content()
                    .frame(minWidth: 240, maxWidth: .infinity, maxHeight: .infinity)
            }
        case .horizontal:
            VSplitView {
                content()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
                content()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
            }
        case nil:
            content()
        }
    }

    private var splitControls: some View {
        Menu {
            Button {
                axisRaw = PaneSplitAxis.vertical.rawValue
            } label: {
                Label("Split Left / Right", systemImage: "rectangle.split.2x1")
            }
            Button {
                axisRaw = PaneSplitAxis.horizontal.rawValue
            } label: {
                Label("Split Top / Bottom", systemImage: "rectangle.split.1x2")
            }
            if axis != nil {
                Divider()
                Button {
                    axisRaw = ""
                } label: {
                    Label("Remove Split", systemImage: "rectangle")
                }
            }
        } label: {
            Image(systemName: axis == nil ? "rectangle.split.2x1" : "rectangle.split.2x1.fill")
                .foregroundStyle(.secondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .padding(6)
        .help("Split this pane")
        .accessibilityIdentifier("splittablePane.\(storageKey).menu")
    }
}
