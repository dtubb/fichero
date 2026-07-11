import FicheroAPIClient
import SwiftUI

// Toolbar, tools menu, and filter menu for OntologyBrowser (#1703).
extension OntologyBrowser {
    /// Entity-type cases shown in the filter menu. Matches
    /// `EntityType-Output` schema (person/location/organization/event/
    /// concept/other) — keep the order stable for sidebar muscle memory.
    struct EntityKindChip {
        let key: String
        let label: String
        let icon: String
    }

    var entityKinds: [EntityKindChip] {
        [
            .init(key: "person", label: "People", icon: "person.2"),
            .init(key: "location", label: "Places", icon: "mappin.circle"),
            .init(key: "organization", label: "Organizations", icon: "building.2"),
            .init(key: "event", label: "Events", icon: "calendar"),
            .init(key: "concept", label: "Concepts", icon: "tag"),
            .init(key: "other", label: "Other", icon: "questionmark.circle")
        ]
    }

    // MARK: - Top Toolbar (matches MiniToolbar pattern used elsewhere)

    var toolbar: some View {
        // The leading "circle.hexagongrid" icon + "Knowledge Graph" text
        // were removed in #981 — the sidebar already labels this
        // destination, and the icon was non-interactive (looked
        // tappable, did nothing). Toolbar now leads straight with
        // actions, ending in the View picker on the right.
        MiniToolbar {
            // Back / forward navigation (#1186)
            Button {
                applyHistoryEntry(navHistory.goBack())
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.plain)
            .disabled(!navHistory.canGoBack)
            .help("Go back (⌘')")
            .keyboardShortcut("'", modifiers: .command)
            Button {
                applyHistoryEntry(navHistory.goForward())
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.plain)
            .disabled(!navHistory.canGoForward)
            .help("Go forward (⌘⇧')")
            .keyboardShortcut("'", modifiers: [.command, .shift])
            Spacer(minLength: 0)
            if let status = toolStatus {
                Text(status)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .transition(.opacity)
            }
            Button {
                showCreateSheet = true
            } label: {
                Image(systemName: "plus")
            }
            .buttonStyle(.plain)
            .help("New entity (#916)")
            Button {
                showSparqlConsole = true
            } label: {
                Image(systemName: "chevron.left.forwardslash.chevron.right")
            }
            .buttonStyle(.plain)
            .help("SPARQL console — query the knowledge graph (W3C, #3298)")
            toolsMenu
            filterMenu
            // The List/Graph/Chart/Timeline/Map switcher is NOT a row of icons
            // in this pane toolbar anymore (#2436). View-mode switching belongs
            // in the main window toolbar / View menu — the focused
            // `OntologyBrowser` publishes `knowledgeGraphViewMode` (see body),
            // which drives `KnowledgeGraphViewModeSection` in the View menu and
            // the iOS toolbar View menu.
            // The manual refresh button was removed in #1007 — the
            // entity list now auto-refreshes when a workflow completes
            // (see `.onChange(of: executionObserver.workflowCompletedCount)`
            // on the list .task below). A visible refresh button signals
            // "the data shown might be stale" — better to keep it fresh.
        }
    }

    /// "Tools" menu — surfaces the post-consolidation /api/kg/* surfaces:
    /// claim+entity embedding and heuristic prediction generation. Each
    /// action runs in a Task and updates `toolStatus` so the user sees
    /// progress in the toolbar without a modal. (#919 5c)
    var toolsMenu: some View {
        Menu {
            Button {
                Task { await runEmbedClaims() }
            } label: {
                Label("Embed claims for semantic search", systemImage: "doc.text.magnifyingglass")
            }
            Button {
                Task { await runEmbedEntities() }
            } label: {
                Label("Embed entities for semantic search", systemImage: "magnifyingglass.circle")
            }
            Divider()
            Button {
                Task { await runHeuristicPredictions() }
            } label: {
                Label("Generate suggested links (heuristic)", systemImage: "wand.and.stars")
            }
        } label: {
            Image(systemName: "wrench.and.screwdriver")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Knowledge graph tools")
    }

    /// Filter menu — Tinderbox-style 'displayed attributes' picker,
    /// shared @AppStorage with the inspector KG tab.
    var filterMenu: some View {
        Menu {
            ForEach(entityKinds, id: \.key) { chip in
                let isHidden = hiddenKinds.contains(chip.key)
                Button {
                    setHidden(chip.key, hidden: !isHidden)
                } label: {
                    Label(chip.label, systemImage: isHidden ? "" : "checkmark")
                }
            }
            Divider()
            Button("Show All") { hiddenKindsCSV = "" }
            Button("Hide All") {
                hiddenKindsCSV = entityKinds
                    .map(\.key)
                    .sorted()
                    .joined(separator: ",")
            }
            Divider()
            Toggle("Suppress OCR noise", isOn: Binding(
                get: { suppressOcrGarbage },
                set: { suppressOcrGarbage = $0 }
            ))
        } label: {
            Image(systemName: hiddenKinds.isEmpty
                    ? "line.3.horizontal.decrease.circle"
                    : "line.3.horizontal.decrease.circle.fill")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Filter entity kinds")
    }

    func runEmbedClaims() async {
        await runTool(label: "Embedding claims") { service in
            let count = try await service.embedClaims()
            return "\(count) claims embedded"
        }
    }

    func runEmbedEntities() async {
        await runTool(label: "Embedding entities") { service in
            let count = try await service.embedEntities()
            return "\(count) entities embedded"
        }
    }

    func runHeuristicPredictions() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        toolStatus = "Generating suggestions…"
        defer {
            Task {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                toolStatus = nil
            }
        }
        do {
            let res = try await library.entityService.generateHeuristicPredictions(topK: 10)
            if res.predictions.isEmpty {
                toolStatus = "No new suggestions"
                pendingPredictions = nil
            } else {
                toolStatus = "\(res.predictions.count) suggested links"
                pendingPredictions = res
            }
        } catch {
            toolStatus = "Failed: \(error.localizedDescription)"
        }
    }

    func runTool(
        label: String,
        action: @escaping (EntityServiceGenerated) async throws -> String
    ) async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        toolStatus = "\(label)…"
        do {
            let result = try await action(library.entityService)
            toolStatus = result
        } catch {
            toolStatus = "Failed: \(error.localizedDescription)"
        }
        // Clear status after a few seconds so the toolbar settles.
        try? await Task.sleep(nanoseconds: 4_000_000_000)
        toolStatus = nil
    }
}
