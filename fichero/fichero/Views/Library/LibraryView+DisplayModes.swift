import SwiftUI

// MARK: - Display Modes Extension

extension LibraryView {
    // MARK: - Icons View (Grid)

    var iconsView: some View {
        let itemMin = CGFloat(max(60, 120 * iconViewScale))
        let itemMax = CGFloat(max(80, 150 * iconViewScale))
        return GeometryReader { geometry in
            // Clamp pinch max so a single thumbnail never exceeds the visible
            // grid width. In the wide content grid this lets us zoom way in;
            // in a narrow sidebar grid the ceiling stays small. Cell width is
            // 100 * scale + ~16 padding, so max ≈ (width - 32) / 100.
            let pinchMax = max(1.0, min(5.0, Double((geometry.size.width - 32) / 100)))
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: itemMin, maximum: itemMax))],
                        alignment: .center,
                        spacing: 20
                    ) {
                        ForEach(filteredDocuments) { doc in
                            DocumentThumbnailView(
                                document: doc,
                                isSelected: selection.contains(doc.id),
                                scale: CGFloat(iconViewScale)
                            )
                            .id(doc.id)
                            .draggable(doc.id)
                            .onTapGesture(count: 2) {
                                handleDoubleClick(doc)
                            }
                            .onTapGesture {
                                handleTap(doc)
                                onRequestFocus()
                            }
                            .contextMenu {
                                documentContextMenu(for: doc)
                            }
                        }
                    }
                    .padding()
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                }
                // In icon mode, ScrollView may consume arrow keys for scrolling first.
                // Handle them at this level so keyboard selection always works.
                .onKeyPress(.upArrow, phases: .down) { _ in
                    handleArrowKey(direction: .upDir)
                }
                .onKeyPress(.downArrow, phases: .down) { _ in
                    handleArrowKey(direction: .down)
                }
                .onKeyPress(.leftArrow, phases: .down) { _ in
                    handleArrowKey(direction: .left)
                }
                .onKeyPress(.rightArrow, phases: .down) { _ in
                    handleArrowKey(direction: .right)
                }
                .onKeyPress(.pageUp, phases: .down) { _ in
                    handleArrowKey(direction: .pageUp)
                }
                .onKeyPress(.pageDown, phases: .down) { _ in
                    handleArrowKey(direction: .pageDown)
                }
                .onMoveCommand { direction in
                    handleMoveCommand(direction)
                }
                // .focusable() here so the .onKeyPress handlers above receive
                // arrow keys (ScrollView would otherwise swallow them). But
                // the default focus ring draws around this whole scroll area
                // at the top of the view — visually misleading since the
                // "focus" semantically belongs to the selected cell.
                // `.focusEffectDisabled()` suppresses the container ring;
                // per-cell focus is already expressed via the accent overlay
                // in DocumentThumbnailView based on `isSelected` (#575).
                .focusable()
                .focusEffectDisabled()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                // Pinch-to-zoom on the trackpad resizes icons live, like
                // Finder's icon view. Clamped 0.5–2.5x to match the toolbar
                // +/- buttons' usable range; persisted via @AppStorage on
                // iconViewScale so the scale survives relaunch.
                // Round to 0.05 steps so LazyVGrid relayouts a few times per
                // gesture instead of every magnification tick — eliminates the
                // jitter without losing perceived smoothness (#782). Max raised
                // 2.5 → 5.0 to match the toolbar +/- range so users can really
                // zoom in on stamps/handwriting (same rationale as #604).
                .gesture(
                    MagnificationGesture()
                        .onChanged { magnitude in
                            let candidate = pinchBaseScale * magnitude
                            let clamped = max(0.5, min(pinchMax, candidate))
                            let stepped = (clamped * 20).rounded() / 20
                            if stepped != iconViewScale {
                                iconViewScale = stepped
                            }
                        }
                        .onEnded { _ in
                            pinchBaseScale = iconViewScale
                        }
                )
                .onChange(of: geometry.size.width) { _, newWidth in
                    let cellWidth = CGFloat(120 * iconViewScale) + 20
                    let availableWidth = newWidth - 32
                    gridColumnCount = max(1, Int(availableWidth / cellWidth))
                    // If the pane just shrank (e.g. a sidebar panel), also
                    // shrink iconViewScale so a single icon can't be wider
                    // than its container.
                    let newPinchMax = max(1.0, min(5.0, Double((newWidth - 32) / 100)))
                    if iconViewScale > newPinchMax {
                        iconViewScale = newPinchMax
                        pinchBaseScale = newPinchMax
                    }
                }
                .onAppear {
                    let cellWidth = CGFloat(120 * iconViewScale) + 20
                    let availableWidth = geometry.size.width - 32
                    gridColumnCount = max(1, Int(availableWidth / cellWidth))

                    // Restored-from-launch selection scroll (#808). On launch
                    // the previous selection is restored but the LazyVGrid
                    // boots scrolled to the top — selected item is offscreen.
                    // Defer one tick so LazyVGrid materialises enough cells
                    // for scrollTo to find the id, then center on it.
                    if let id = selection.first {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                proxy.scrollTo(id, anchor: .center)
                            }
                        }
                    }
                }
                .onChange(of: listScrollTarget) { _, id in
                    guard let id else { return }
                    // Arrow-key nav: minimal scroll. anchor: nil = "scroll just
                    // enough to make visible, no-op if already visible." This
                    // is what fixes #769 — earlier code used .center which
                    // recentered on every keypress.
                    withAnimation(.easeInOut(duration: 0.15)) {
                        proxy.scrollTo(id, anchor: nil)
                    }
                    listScrollTarget = nil
                }
                .onChange(of: listScrollCenterTarget) { _, id in
                    guard let id else { return }
                    // Double-click / layout-change: force center so the user
                    // can find the item they just opened in the now-shrunken
                    // grid pane.
                    withAnimation(.easeInOut(duration: 0.15)) {
                        proxy.scrollTo(id, anchor: .center)
                    }
                    listScrollCenterTarget = nil
                }
            }
        }
    }

    // MARK: - List View (Mail-style compact rows)
    // Uses ScrollView+LazyVStack instead of List to avoid AppKit NSTableView
    // intercepting arrow key events before our .onKeyPress handlers fire.

    var listView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(filteredDocuments) { doc in
                        MailStyleRow(
                            document: doc,
                            isSelected: selection.contains(doc.id),
                            visibleEntityTypes: listVisibleEntityTypes
                        ) { tag in
                            searchText = tag
                            showFilterBar = true
                        }
                        .id(doc.id)
                        .draggable(doc.id)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(
                            selection.contains(doc.id)
                                ? Color.accentColor.opacity(0.12)
                                : Color.clear
                        )
                        .contentShape(Rectangle())
                        .onTapGesture(count: 2) {
                            handleDoubleClick(doc)
                        }
                        .onTapGesture {
                            handleTap(doc)
                            onRequestFocus()
                        }
                        .contextMenu {
                            documentContextMenu(for: doc)
                        }

                        Divider()
                            .padding(.leading, 12)
                    }
                }
            }
            .onChange(of: listScrollTarget) { _, id in
                guard let id else { return }
                proxy.scrollTo(id, anchor: nil)
                listScrollTarget = nil
            }
            .onAppear {
                // Restored-from-launch selection scroll for list view (#808).
                if let id = selection.first {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            proxy.scrollTo(id, anchor: .center)
                        }
                    }
                }
            }
        }
        .overlay(alignment: .topTrailing) { entityFilterMenu }
    }

    /// Set of entity-type ids the user wants visible in list rows.
    /// Drives `MailStyleRow` → `ArtifactEntitiesView` filtering. (#519
    /// follow-up)
    var listVisibleEntityTypes: Set<String> {
        var set = Set<String>()
        if showPeopleEntities { set.insert("people") }
        if showPlacesEntities { set.insert("places") }
        if showOrganizationsEntities { set.insert("organizations") }
        if showDatesEntities { set.insert("dates") }
        if showEventsEntities { set.insert("events") }
        if showKeywordsEntities { set.insert("keywords") }
        return set
    }

    /// Top-right filter menu — toggles per-entity-type visibility for
    /// the list-row lozenge rows. Daniel: 'in the top right of the list
    /// view a way to filter what artefacts and entitites to show.'
    @ViewBuilder
    var entityFilterMenu: some View {
        Menu {
            Toggle("People", isOn: $showPeopleEntities)
            Toggle("Places", isOn: $showPlacesEntities)
            Toggle("Organizations", isOn: $showOrganizationsEntities)
            Toggle("Dates", isOn: $showDatesEntities)
            Toggle("Events", isOn: $showEventsEntities)
            Toggle("Keywords", isOn: $showKeywordsEntities)
            Divider()
            Button("Show All") {
                showPeopleEntities = true
                showPlacesEntities = true
                showOrganizationsEntities = true
                showDatesEntities = true
                showEventsEntities = true
                showKeywordsEntities = true
            }
            Button("Hide All") {
                showPeopleEntities = false
                showPlacesEntities = false
                showOrganizationsEntities = false
                showDatesEntities = false
                showEventsEntities = false
                showKeywordsEntities = false
            }
        } label: {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .imageScale(.medium)
                .padding(8)
                .background(.ultraThinMaterial, in: Circle())
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .padding(8)
        .help("Filter entity types shown")
    }

    // MARK: - Table View (Sortable columns + Mac-native column customization)

    var tableView: some View {
        // Native column customization: right-click on any column header
        // surfaces SwiftUI's built-in show/hide + reorder menu. Each
        // column needs a stable .customizationID; default visibility
        // matches the prior @SceneStorage defaults so users see the
        // same starting layout. Daniel: 'we want this in the mac way
        // which is a contextual menu in the table view header.' (#519)
        Table(
            filteredDocuments,
            selection: $selection,
            sortOrder: $sortOrder,
            columnCustomization: $tableColumnCustomization
        ) {
            TableColumn("Name", value: \Document.name) { doc in
                tableCellView(for: "name", document: doc)
            }
            .width(min: 150, ideal: 200)
            .customizationID("name")
            .disabledCustomizationBehavior(.visibility)  // Always visible

            TableColumn("Status", value: \Document.status.rawValue) { doc in
                tableCellView(for: "status", document: doc)
            }
            .width(min: 80, ideal: 100)
            .customizationID("status")

            TableColumn("Output") { doc in
                tableCellView(for: "output", document: doc)
            }
            .width(min: 150, ideal: 250)
            .customizationID("output")

            TableColumn("Created", value: \Document.createdAt) { doc in
                tableCellView(for: "createdDate", document: doc)
            }
            .width(min: 80, ideal: 100)
            .customizationID("createdDate")

            // Per-entity-type columns (#519). Each renders FlowLayout
            // lozenges via ArtifactEntityCell for that doc's artifacts
            // of one type. All hidden by default; users opt in via the
            // column-header right-click menu (Mac native).
            //
            // SwiftUI's TableColumnBuilder caps at 10 children — we
            // dropped path/modifiedDate/size/artifacts(combined) to fit.
            // Those rarely-used metadata columns can come back via
            // computed-property column groups in a follow-up if needed.
            TableColumn("People") { doc in
                tableCellView(for: "people", document: doc)
            }
            .width(min: 120, ideal: 200)
            .customizationID("people")
            .defaultVisibility(.hidden)

            TableColumn("Places") { doc in
                tableCellView(for: "places", document: doc)
            }
            .width(min: 120, ideal: 180)
            .customizationID("places")
            .defaultVisibility(.hidden)

            TableColumn("Organizations") { doc in
                tableCellView(for: "organizations", document: doc)
            }
            .width(min: 120, ideal: 180)
            .customizationID("organizations")
            .defaultVisibility(.hidden)

            TableColumn("Dates") { doc in
                tableCellView(for: "dates", document: doc)
            }
            .width(min: 100, ideal: 140)
            .customizationID("dates")
            .defaultVisibility(.hidden)

            TableColumn("Events") { doc in
                tableCellView(for: "events", document: doc)
            }
            .width(min: 120, ideal: 200)
            .customizationID("events")
            .defaultVisibility(.hidden)

            TableColumn("Keywords") { doc in
                tableCellView(for: "keywords", document: doc)
            }
            .width(min: 120, ideal: 200)
            .customizationID("keywords")
            .defaultVisibility(.hidden)
        }
        .tableStyle(.inset)
        .contextMenu(forSelectionType: String.self) { items in
            if let firstId = items.first,
               let doc = filteredDocuments.first(where: { $0.id == firstId }) {
                documentContextMenu(for: doc)
            }
        }
        .onTapGesture(count: 2) {
            if let firstId = selection.first,
               let doc = filteredDocuments.first(where: { $0.id == firstId }) {
                handleDoubleClick(doc)
            }
        }
    }

    // MARK: - Map View (Tinderbox-style canvas)

    var mapView: some View {
        ScrollView([.horizontal, .vertical]) {
            ZStack(alignment: .topLeading) {
                // Grid background (fills the scaled canvas frame)
                MapGridBackground()

                // Document cards at scaled positions
                ForEach(filteredDocuments) { doc in
                    let base = mapPositions[doc.id] ?? defaultMapPosition(for: doc)
                    let pos = CGPoint(
                        x: base.x * CGFloat(mapCanvasScale),
                        y: base.y * CGFloat(mapCanvasScale)
                    )
                    MapCard(
                        document: doc,
                        isSelected: selection.contains(doc.id),
                        position: pos
                    )
                    .onTapGesture(count: 2) {
                        handleDoubleClick(doc)
                    }
                    .onTapGesture {
                        handleTap(doc)
                    }
                    .gesture(
                        DragGesture()
                            .onChanged { value in
                                // Store in unscaled document coordinates
                                mapPositions[doc.id] = CGPoint(
                                    x: value.location.x / CGFloat(mapCanvasScale),
                                    y: value.location.y / CGFloat(mapCanvasScale)
                                )
                            }
                    )
                    .contextMenu {
                        documentContextMenu(for: doc)
                    }
                }
            }
            .frame(
                width: mapCanvasWidth * CGFloat(mapCanvasScale),
                height: mapCanvasHeight * CGFloat(mapCanvasScale)
            )
        }
        .background(Color(.textBackgroundColor))
        .onAppear {
            initializeMapPositions()
        }
    }

    // MARK: - Map Helpers

    func initializeMapPositions() {
        // Only initialize if not already set
        for (index, doc) in filteredDocuments.enumerated() where mapPositions[doc.id] == nil {
            let row = index / 4
            let col = index % 4
            mapPositions[doc.id] = CGPoint(
                x: 100 + CGFloat(col) * 200,
                y: 100 + CGFloat(row) * 150
            )
        }
    }

    func defaultMapPosition(for doc: Document) -> CGPoint {
        guard let index = filteredDocuments.firstIndex(where: { $0.id == doc.id }) else {
            return CGPoint(x: 100, y: 100)
        }
        let row = index / 4
        let col = index % 4
        return CGPoint(x: 100 + CGFloat(col) * 200, y: 100 + CGFloat(row) * 150)
    }

    private var mapCanvasWidth: CGFloat {
        let maxX = mapPositions.values.map(\.x).max() ?? 0
        let cols = min(3, max(0, filteredDocuments.count - 1))
        let countWidth = 100 + CGFloat(cols) * 200 + 200
        return max(1200, max(maxX + 200, countWidth))
    }

    private var mapCanvasHeight: CGFloat {
        let maxY = mapPositions.values.map(\.y).max() ?? 0
        let rows = filteredDocuments.isEmpty ? 0 : (filteredDocuments.count - 1) / 4
        let countHeight = 100 + CGFloat(rows) * 150 + 200
        return max(800, max(maxY + 200, countHeight))
    }
}
