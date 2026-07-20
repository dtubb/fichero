import SwiftUI

// MARK: - ContentView Inspector Container Extension
// Agent: ViewBuilderAgent
// Responsibility: Detail-column toolbar content and the docked/pushed inspector
// container routing. Split out of ContentView+RootLayout.swift to keep each
// file under the file_length limit.

extension ContentView {
    /// Detail-column toolbar content split out to keep the `NavigationSplitView`
    /// detail closure small enough for the Swift type-checker.
    /// Internal (not private): referenced from `detailColumn` in
    /// ContentView+RootLayout.swift — `private` is file-scoped.
    @ToolbarContentBuilder
    var detailToolbarContent: some ToolbarContent {
        contentPaneToolbarContent
        // Inspector toggle in the content section. .automatic on the detail
        // column view lands in the content-column toolbar section (#2309).
        trailingToolbarContent
        // Centred context label. .principal on the detail column centres
        // within the content section — visually near window centre at
        // typical sidebar widths (#2309).
        principalToolbarContent
    }

    /// Internal (not private): referenced from `mainContentView` in
    /// ContentView+RootLayout.swift — `private` is file-scoped.
    @ViewBuilder
    var inspectorContainerView: some View {
        if usesDockedInspector {
            #if os(visionOS)
            detailView
                // Inspector toggle in the INSPECTOR SECTION (far right).
                // Attaching to the inspector panel content (rather than the
                // detail column) places the button in the trailing inspector
                // section of the unified toolbar instead of the content
                // section. NavigationSplitView does not auto-remove column
                // toolbar contributions when a column is hidden, so the
                // toggle remains visible even when the inspector is closed
                // — same mechanism as the sidebar-section buttons (#2309).
                .toolbar {
                    if showInspectorToggle {
                        ToolbarItem(id: ContentToolbarID.inspectorToggle, placement: .primaryAction) {
                            inspectorToggleButton
                        }
                    }
                }
            #else
            detailView
                // Inspector toggle in the INSPECTOR SECTION (far right).
                // Attaching to the inspector panel content (rather than the
                // detail column) places the button in the trailing inspector
                // section of the unified NSToolbar instead of the content
                // section. NavigationSplitView does not auto-remove column
                // toolbar contributions when a column is hidden, so the
                // toggle remains visible even when the inspector is closed
                // — same mechanism as the sidebar-section buttons (#2309).
                .toolbar {
                    if showInspectorToggle {
                        ToolbarItem(id: ContentToolbarID.inspectorToggle, placement: .primaryAction) {
                            inspectorToggleButton
                        }
                    }
                }
                .inspectorColumnWidth(
                    min: CGFloat(ContentView.inspectorMinWidth),
                    ideal: 300,
                    max: CGFloat(ContentView.inspectorMaxWidth)
                )
            #endif
        } else {
            // Compact width (iPhone): the adaptive presenter routes the
            // inspector into the collapsed navigation stack, so it pushes from
            // the right and participates in back-swipe / back-button history.
            // This branch supplies ONLY the inspector content; the presenter
            // owns the stack-vs-docked choice outside this builder.
            detailView
        }
    }
}
