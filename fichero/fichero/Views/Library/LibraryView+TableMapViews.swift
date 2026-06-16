import SwiftUI

// MARK: - Table + Map Display Modes

extension LibraryView {

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
        .alternatingRowBackgrounds()
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
