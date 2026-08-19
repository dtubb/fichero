import SwiftUI

// MARK: - Resident toolbar search field (#4604)
//
// Split from ContentView+Toolbar.swift for file_length; cohesion: everything
// here is the top-right search field and its merged mode menu.

extension ContentView {
    // MARK: Resident search field (#4604)

    /// The always-there window search: magnifier-as-menu + field + clear.
    private var toolbarSearchField: some View {
        HStack(spacing: 4) {
            searchModeMenu

            TextField("Search your library", text: $toolbarSearchText)
                .textFieldStyle(.plain)
                .font(.callout)
                .frame(width: 180)
                .focused($toolbarSearchFieldFocused)
                .onSubmit { runToolbarSearch(toolbarSearchText) }

            if !toolbarSearchText.isEmpty {
                Button {
                    // Same dismissal semantics the toggle had: emptying the
                    // field exits transient-search presentation so the
                    // library can't silently show results for an invisible
                    // query (#4521 rule, field just never hides now).
                    setSearchFieldVisible(false)
                } label: {
                    Image(systemName: ToolbarSymbols.clearField)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
                .help("Clear search")
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(.quaternary.opacity(0.5))
        )
        .help("Search the library — the magnifier picks the mode")
    }

    /// ONE mode control on the magnifier (#4604 §4.2): what the words mean
    /// (Ask vs Keyword) and how matching runs (Hybrid / Semantic / Full
    /// Text) — previously two controls in two different bars.
    private var searchModeMenu: some View {
        Menu {
            Section("Mode") {
                ForEach(SearchFieldMode.allCases, id: \.self) { mode in
                    Button {
                        searchFieldModeRaw = mode.rawValue
                    } label: {
                        if searchFieldModeRaw == mode.rawValue {
                            Label(mode == .ask ? "Ask" : "Keyword", systemImage: "checkmark")
                        } else {
                            Text(mode == .ask ? "Ask" : "Keyword")
                        }
                    }
                }
            }
            Section("Method") {
                ForEach(
                    [("hybrid", "Hybrid"), ("semantic", "Semantic"), ("fulltext", "Full Text")],
                    id: \.0
                ) { value, label in
                    Button {
                        transientSearchType = value
                    } label: {
                        if transientSearchType == value {
                            Label(label, systemImage: "checkmark")
                        } else {
                            Text(label)
                        }
                    }
                }
            }
        } label: {
            Image(systemName: searchFieldModeRaw == SearchFieldMode.ask.rawValue
                ? "sparkle.magnifyingglass" : ToolbarSymbols.findField)
                .foregroundStyle(.secondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Search mode: Ask or Keyword; Hybrid, Semantic, or Full Text")
    }
}
