import SwiftUI

// MARK: - Toolbar item identity

enum ContentToolbarID {
    static let navigationBack = "fichero.nav.back"
    static let navigationForward = "fichero.nav.forward"
    static let inspectorToggle = "fichero.inspectorToggle"
    static let compactInspectorToggle = "fichero.inspectorToggle.compact"
    static let activityStatus = "fichero.activityStatus"
    static let viewMenu = "fichero.viewMenu"
    static let viewDisplayMode = "fichero.viewDisplayMode"
    static let previewPaneToggle = "fichero.previewPane.toggle"
    static let readingPaneToggle = "fichero.readingPane.toggle"
    static let breadcrumb = "fichero.breadcrumb"
}

// MARK: - Toolbar Content
//
// Members called from ContentView.swift's body (contentPane/trailing/principal
// toolbar content, inspectorToggleButton, syncFocusedDocumentSelection) are
// internal, not private: `private` is FILE-scoped, and the body now lives in a
// different file. The rest stay private to this file.

extension ContentView {
    @ViewBuilder
    func toolbarToggleIcon(_ systemName: String, isActive: Bool) -> some View {
        Image(systemName: systemName)
            .symbolVariant(isActive ? .fill : .none)
            .padding(.horizontal, 5)
            .padding(.vertical, 3)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(isActive ? Color.primary.opacity(0.1) : Color.clear)
            )
    }

    // MARK: Zoned toolbar (Mail-style)
    @ToolbarContentBuilder
    var mainToolbarContent: some ToolbarContent {
        leadingToolbarContent
    }

    /// LEADING zone: back/forward history navigation in the content-column toolbar.
    @ToolbarContentBuilder
    private var leadingToolbarContent: some ToolbarContent {
        ToolbarItem(id: ContentToolbarID.navigationBack, placement: .navigation) {
            Button {
                navigateBack()
            } label: {
                Label("Back", systemImage: "chevron.backward")
            }
            .help("Back (⌘')")
            .keyboardShortcut("'", modifiers: [.command])
            .disabled(!navigationHistory.canGoBack)
        }

        ToolbarItem(id: ContentToolbarID.navigationForward, placement: .navigation) {
            Button {
                navigateForward()
            } label: {
                Label("Forward", systemImage: "chevron.forward")
            }
            .help("Forward (⌘⇧')")
            .keyboardShortcut("'", modifiers: [.command, .shift])
            .disabled(!navigationHistory.canGoForward)
        }
    }

    /// TRAILING zone: activity status (#2309).
    /// The inspector toggle moved to the `.inspector()` panel's toolbar so
    /// macOS places it in the inspector section (far right) rather than the
    /// content section (see `mainContentView`).
    @ToolbarContentBuilder
    var trailingToolbarContent: some ToolbarContent {
        #if !os(macOS)
        if showInspectorToggle && !usesDockedInspector {
            ToolbarItem(id: ContentToolbarID.compactInspectorToggle, placement: .topBarTrailing) {
                inspectorToggleButton
            }
        }
        #endif

        // Activity / error status — sits between the title and the inspector section.
        ToolbarItem(id: ContentToolbarID.activityStatus, placement: .automatic) {
            HStack(spacing: 6) {
                if isImporting {
                    ProgressView()
                        .controlSize(.small)
                        .help(importProgress ?? "Importing…")
                }
                if importError != nil {
                    Image(systemName: "exclamationmark.circle.fill")
                        .foregroundStyle(.red)
                        .help(importError ?? "Import error")
                        .onTapGesture { importError = nil }
                }
            }
        }

        // Show/hide-panes + view-mode control on every platform's toolbar,
        // including Mac (previously menu-bar only) so it matches iPad/iOS (#2493).
        ToolbarItem(id: ContentToolbarID.viewMenu, placement: .primaryAction) {
            platformViewMenuButton
        }
    }

    @ToolbarContentBuilder
    var contentPaneToolbarContent: some ToolbarContent {
        // The preview/reading pane toggles only make sense in the multi-pane
        // reading workspace. In the compact (iPhone) flow the reader is a single
        // navigation stack, not split panes, so the toggles do nothing and are
        // hidden (#2813).
        if supportsReadingWorkspace
            && !Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
            if showViewModePicker && availableViewDisplayModes.count > 1 {
                ToolbarItem(id: ContentToolbarID.viewDisplayMode, placement: .automatic) {
                    viewDisplayModeMenu
                }
            }

            ToolbarItem(id: ContentToolbarID.previewPaneToggle, placement: .automatic) {
                Button {
                    setCanvasPaneVisible(!showDocumentCanvas)
                } label: {
                    Label("Preview Pane", systemImage: showDocumentCanvas ? "rectangle.center.inset.filled" : "rectangle")
                }
                .help(showDocumentCanvas ? "Hide preview pane" : "Show preview pane")
            }

            ToolbarItem(id: ContentToolbarID.readingPaneToggle, placement: .automatic) {
                Button {
                    setReadingPaneVisible(!showReadingPane)
                } label: {
                    Label("Reading Pane", systemImage: showReadingPane ? "text.book.closed.fill" : "text.book.closed")
                }
                .help(showReadingPane ? "Hide reading pane" : "Show reading pane")
            }
        }
    }

    private var viewDisplayModeMenu: some View {
        Menu {
            ForEach(availableViewDisplayModes) { mode in
                Button {
                    updateViewDisplayMode(mode)
                } label: {
                    Label(mode.label, systemImage: mode.icon)
                }
            }
        } label: {
            Label(viewDisplayMode.label, systemImage: viewDisplayMode.icon)
        }
        .help("Choose how library items are shown")
    }

    @ViewBuilder
    private var platformViewMenuButton: some View {
        Menu {
            ViewMenuCommands()
                .environment(viewSettings)
        } label: {
            Label("View", systemImage: "rectangle.split.3x1")
        }
        .help("Choose visible panes and document views")
    }

    var inspectorToggleButton: some View {
        Button {
            withAnimation(FrameAnimation.snappy) {
                showInspectorSidebar.toggle()
            }
        } label: {
            Label {
                Text("Inspector")
            } icon: {
                toolbarToggleIcon("sidebar.right", isActive: showInspectorSidebar)
            }
        }
        .help(showInspectorSidebar ? "Hide Inspector (⌘⌥I)" : "Show Inspector (⌘⌥I)")
    }

    /// PRINCIPAL zone: breadcrumb lozenge + scoped search (#2309/#2039).
    /// Layout: [Library Name] > [item icon + title] [search current content]
    /// The whole breadcrumb sits in a subtle rounded-rect lozenge with
    /// extra horizontal padding so it reads as a single interactive label.
    @ToolbarContentBuilder
    var principalToolbarContent: some ToolbarContent {
        // The breadcrumb lozenge + fixed 220pt search field is Mac/iPad window
        // chrome. At compact width (iPhone) it overflows the nav bar, so it's
        // dropped — the nav title carries the context and search moves to the
        // native `.searchable` field instead (#2814).
        if horizontalSizeClass != .compact {
            ToolbarItem(id: ContentToolbarID.breadcrumb, placement: .principal) {
                let libraryName: String? = {
                guard case .library(let doc) = viewMode, doc != nil else { return nil }
                return LibraryManager.shared.getLibrary(id: windowState.libraryId)?.displayName
            }()

            HStack(spacing: 4) {
                HStack(spacing: 4) {
                    if let libraryName {
                        HStack(spacing: 3) {
                            Image(systemName: "books.vertical")
                                .imageScale(.small)
                            Text(libraryName)
                                .font(.subheadline)
                        }
                        .foregroundStyle(.secondary)

                        Image(systemName: "chevron.right")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }

                    HStack(spacing: 3) {
                        Image(systemName: toolbarIcon)
                            .imageScale(.small)
                        Text(toolbarTitle)
                            .font(.headline)
                            .lineLimit(1)
                    }
                    .foregroundStyle(.primary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.primary.opacity(0.06))
                )
                // Search field removed (#3037) — now the native `.searchable`
                // bar (ToolbarSearchableModifier). The breadcrumb lozenge above
                // stays as the principal-zone context chrome.
                }
            }
        }
    }

    func syncFocusedDocumentSelection(_ document: Document?) {
        if let document {
            focusedDocument.select(document, libraryId: windowState.libraryId)
        } else {
            focusedDocument.clear()
        }
    }
}
