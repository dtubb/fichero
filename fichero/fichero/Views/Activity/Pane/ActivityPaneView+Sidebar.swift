import SwiftUI

// The Activity window's sidebar, split out of ActivityPaneView.swift (SwiftLint's size limits): the source list, its Models
// tree and what a pick in it shows.

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
        .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 300)
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
}
