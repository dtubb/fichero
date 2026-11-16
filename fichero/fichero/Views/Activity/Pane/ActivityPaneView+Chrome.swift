import SwiftUI

/// The Activity pane's chrome: the window's sidebar, the head, the filter and the status bar.
extension ActivityPaneView {
    /// The Activity window's sidebar (`activity.window.sidebar`, decision 32): the items as a source list; choosing one is
    /// choosing what the centre lists and its columns. Each says how many of its rows need the person.
    var sidebar: some View {
        List(selection: Binding(get: { sidebarPick ?? "tab:\(prefs.tab.rawValue)" }, set: pickInSidebar)) {
            Section("Activity") {
                ForEach(ActivityPane.Tab.sidebarWork) { tab in sidebarRow(tab) }
            }
            Section("Resources") {
                ForEach(ActivityPane.Tab.sidebarResources) { tab in sidebarRow(tab) }
            }
            // Models by where they run (decision 33): place › provider › model, each model's icon filled while loaded, a green
            // dot while it works, its memory beside it.
            if !models.isEmpty {
                Section("Models") {
                    ForEach(ActivityModelEntry.tree(models), id: \.place) { place in
                        DisclosureGroup {
                            ForEach(place.providers, id: \.name) { provider in
                                DisclosureGroup {
                                    ForEach(provider.models) { model in modelRow(model) }
                                } label: {
                                    Label(provider.name, systemImage: "building.2").tag("provider:\(provider.name)")
                                }
                            }
                        } label: {
                            Label(place.place.title, systemImage: place.place.icon)
                        }
                    }
                }
            }
            Section {
                sidebarRow(.archived)
            }
        }
        .listStyle(.sidebar)
        // The column's range is its width below, never its rows' (#6661, `ActivityPaneView+WindowLayout.swift`).
        .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
        .navigationSplitViewColumnWidth(min: Self.sidebarWidths.lowerBound, ideal: Self.sidebarIdealWidth,
                                        max: Self.sidebarWidths.upperBound)
        .accessibilityIdentifier("activity.sidebar")
        .task(id: libraries.map(\.id)) { await readModelsOften() }
    }

    func modelRow(_ model: ActivityModelEntry) -> some View {
        HStack(spacing: 6) {
            Image(systemName: model.symbol)
                .foregroundStyle(model.loaded ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
            Text(model.name).lineLimit(1)
            Spacer(minLength: 4)
            if model.active {
                Circle().fill(.green).frame(width: 7, height: 7)
                    .symbolEffect(.pulse)
                    .accessibilityLabel("Working")
            }
            Text(model.memoryWords).font(.caption).foregroundStyle(.secondary).monospacedDigit()
        }
        .help("\(model.provider) · \(model.loaded ? "loaded" : "not loaded")\(model.active ? " · working" : "") · "
              + "\(model.pagesToday) pages, \(model.callsToday) calls today · memory \(model.memoryWords)")
        .tag("model:\(model.id)")
        .accessibilityIdentifier("activity.sidebar.model.\(model.name)")
    }

    /// A sidebar pick: an item shows its rows; a model or a provider lists the rows that ran on it (the filter, by model).
    func pickInSidebar(_ pick: String?) {
        guard let pick else { return }
        sidebarPick = pick
        if pick.hasPrefix("tab:"), let tab = ActivityPane.Tab(rawValue: String(pick.dropFirst(4))) {
            show(tab)
            update { $0.filter = "" }
        } else if pick.hasPrefix("model:"), let model = models.first(where: { "model:\($0.id)" == pick }) {
            show(.runs)
            update { $0.filter = "model: \(model.name)" }
        } else if pick.hasPrefix("provider:") {
            show(.runs)
            update { $0.filter = "model: \(pick.dropFirst(9))" }
        }
    }

    /// The models of the open projects, read every ten seconds while the window shows: loaded and working change often.
    func readModelsOften() async {
        while !Task.isCancelled {
            var lists: [[ActivityModelEntry]] = []
            for library in libraries {
                if let one = try? await library.activityService.models() { lists.append(one) }
            }
            models = ActivityModelEntry.merged(lists)
            try? await Task.sleep(for: .seconds(10))
        }
    }

    func sidebarRow(_ tab: ActivityPane.Tab) -> some View {
        let needsYou = tab == .runs ? ActivityPane.needsYouCount(allRows) : 0
        return Label(tab.title, systemImage: tab.icon)
            .badge(needsYou)
            .tag("tab:\(tab.rawValue)")
            .accessibilityIdentifier("activity.sidebar.\(tab.rawValue)")
    }

    /// Select the row a Show in Activity asked for, once it is listed.
    /// Select every row asked for that is listed (the launch alert's Choose…: the rows the quit stopped).
    func selectAll(_ wanted: [ActivitySelection]?) {
        guard let wanted, !wanted.isEmpty else { return }
        let ids = ActivityPane.rowIds(for: wanted, in: allRows)
        guard !ids.isEmpty else { return }
        selection = ids
        onRevealed()
    }

    func select(_ wanted: ActivitySelection?) {
        guard let wanted else { return }
        let ids = Set(allRows.filter { $0.selection == wanted }.map(\.id))
        guard !ids.isEmpty else { return }
        selection = ids
        onRevealed()
    }

    // MARK: - Head, filter, status bar

    var head: some View {
        PaneHead(
            crumbs: [PaneCrumb(id: "activity", title: "Activity", icon: PaneSpec.Kind.activity.icon)],
            selector: {
                PaneKindSelector(
                    kindTitle: PaneSpec.Kind.activity.title, kindIcon: PaneSpec.Kind.activity.icon,
                    currentKind: .activity, lenses: ActivityPane.Tab.allCases,
                    lensTitle: { (tab: ActivityPane.Tab) in tab.title },
                    lensIcon: { (tab: ActivityPane.Tab) in tab.icon },
                    lens: Binding(get: { prefs.tab }, set: show)
                )
            },
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
    }

    /// The window's history, read now and once a minute while the window shows (`GET /api/activity/history`).
    func readHistoryEachMinute() async {
        guard !showsHead else { return }
        while !Task.isCancelled {
            var read: [ActivityHistoryFigures] = []
            for library in libraries {
                if let one = try? await library.activityService.history() { read.append(one) }
            }
            history = ActivityBottomPanel.merged(read)
            try? await Task.sleep(for: .seconds(60))
        }
    }

    /// The pane's one bottom bar, the app's (`activity.pane.bottom-bar-like-every-pane`, #6588): the Filter field with what the
    /// list shows in its menu, and the status figures. The columns are chosen from a column header's menu, their widths kept
    /// (`activity.pane.columns-from-the-header`, decision 35).
    var bottomBar: some View {
        PaneFilterBar(placement: .bottom) {
            PaneFilterField(text: Binding(get: { prefs.filter }, set: { value in update { $0.filter = value } }),
                            prompt: "Filter: model: Kraken state: failed", accessibilityID: "activity.filter") {
                Toggle("Show Archived", isOn: $showArchived)
                Divider()
                Button("Failed") { update { $0.filter = "state: failed" } }
                Button("Today") { update { $0.filter = "date: today" } }
                Button("Started Automatically") { update { $0.filter = "started by: automatic" } }
            }
            .frame(maxWidth: 360)
            Spacer(minLength: 8)
            // The window's figures are its bottom panel's; the bar keeps the notice there, the whole line in a main window's pane.
            Text((showsHead ? [statusBarText, notice] : [notice]).compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary).monospacedDigit().lineLimit(1)
                .accessibilityIdentifier("activity.statusbar")
            if showsHead { moreMenu }
        }
    }

    /// The More menu: Show Archived, Archive Finished… and Archive Failed (`activity.window.toolbar-verbs`), the window's
    /// toolbar's, and the bottom bar's in a main window's pane.
    var moreMenu: some View {
        Menu {
            Toggle("Show Archived", isOn: $showArchived)
            Button("Archive Finished…") { confirmingArchiveFinished = true }
            Button("Archive Failed") { Task { await archiveFailed() } }
        } label: {
            Label("More", systemImage: "ellipsis.circle")
        }
        .help("Show Archived, Archive Finished…, Archive Failed")
        .accessibilityIdentifier("activity.more")
    }

    /// "3 running · 12 waiting · $3.20 today", Finder style, and "Automatic work paused" while it is.
    var statusBarText: String {
        let rows = allRows
        let today = rows.filter { row in (row.started ?? row.ended).map { Calendar.current.isDateInToday($0) } ?? row.phase.isLive }
        let spent = today.compactMap(\.costUsd).reduce(0, +)
        let counts = ActivityTrail.statusBar(running: rows.filter { $0.phase == .running }.count,
                                             waiting: rows.filter { $0.phase == .waiting }.count,
                                             spentTodayUsd: spent > 0 ? spent : nil)
        let paused = libraries.contains { $0.activityStore.backgroundMode == .paused }
        return paused ? counts + " · Automatic work paused" : counts
    }
}
