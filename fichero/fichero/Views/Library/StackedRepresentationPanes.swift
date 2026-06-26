import SwiftUI

/// A pane that can split vertically into **two representation tabs, one above the
/// other** (#2254, reform master plan §E — Daniel: "two tabs of the webkit view /
/// document inspector, one above the other").
///
/// Collapsed, it shows a single representation chosen from a `Picker`. Split, it
/// becomes a `VSplitView` of two independently-selectable representations stacked
/// vertically — e.g. the rendered WebKit view above and the markdown source below,
/// or two inspector facets at once. A toggle in each pane's header flips between
/// the two layouts; the bottom selection seeds itself to a *different* tab than
/// the top on first split so the user immediately sees two representations.
///
/// Generic over the caller's representation type so it reuses the existing detail
/// content (`paneContent`) rather than re-hosting a parallel viewer — the same
/// "generalize, don't rebuild" spine as the detachable detail scenes.
struct StackedRepresentationPanes<Tab: Hashable, PaneContent: View>: View {
    /// The available representations, in menu order.
    let tabs: [Tab]
    /// Human label + SF Symbol for a representation.
    let label: (Tab) -> (title: String, systemImage: String)
    /// Builds the view for a representation. Called once per visible pane.
    @ViewBuilder let paneContent: (Tab) -> PaneContent

    @State private var topSelection: Tab
    @State private var bottomSelection: Tab
    @State private var isSplit = false

    init(
        tabs: [Tab],
        initialSelection: Tab,
        label: @escaping (Tab) -> (title: String, systemImage: String),
        @ViewBuilder paneContent: @escaping (Tab) -> PaneContent
    ) {
        self.tabs = tabs
        self.label = label
        self.paneContent = paneContent
        _topSelection = State(initialValue: initialSelection)
        // Seed the second pane to a *different* representation when available, so
        // the first split is immediately useful (two things, not one twice).
        let other = tabs.first { $0 != initialSelection } ?? initialSelection
        _bottomSelection = State(initialValue: other)
    }

    var body: some View {
        if isSplit {
            PlatformVSplitView {
                pane(selection: $topSelection, canToggleSplit: true)
                    .frame(minHeight: 120)
                pane(selection: $bottomSelection, canToggleSplit: false)
                    .frame(minHeight: 120)
            }
        } else {
            pane(selection: $topSelection, canToggleSplit: true)
        }
    }

    @ViewBuilder
    private func pane(selection: Binding<Tab>, canToggleSplit: Bool) -> some View {
        VStack(spacing: 0) {
            paneHeader(selection: selection, canToggleSplit: canToggleSplit)
            Divider()
            paneContent(selection.wrappedValue)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private func paneHeader(selection: Binding<Tab>, canToggleSplit: Bool) -> some View {
        HStack(spacing: 8) {
            Picker("Representation", selection: selection) {
                ForEach(tabs, id: \.self) { tab in
                    let item = label(tab)
                    Label(item.title, systemImage: item.systemImage).tag(tab)
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .fixedSize()

            Spacer()

            if canToggleSplit {
                Button {
                    isSplit.toggle()
                } label: {
                    Label(
                        isSplit ? "Merge Panes" : "Split Pane",
                        systemImage: isSplit
                            ? "rectangle"
                            : "rectangle.split.1x2"
                    )
                }
                .buttonStyle(.borderless)
                .labelStyle(.iconOnly)
                .help(
                    isSplit
                        ? "Show a single representation"
                        : "Stack a second representation below this one"
                )
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .font(.subheadline)
    }
}

#Preview("Stacked representation panes") {
    StackedRepresentationPanes(
        tabs: ["Rendered", "Markdown", "HTML"],
        initialSelection: "Rendered",
        label: { tab in
            switch tab {
            case "Rendered": return ("Rendered", "doc.richtext")
            case "Markdown": return ("Markdown", "text.alignleft")
            default: return ("HTML", "chevron.left.forwardslash.chevron.right")
            }
        },
        paneContent: { tab in
            ContentUnavailableView(tab, systemImage: "doc")
        }
    )
    .frame(width: 360, height: 520)
}
