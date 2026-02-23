import SwiftUI

// MARK: - Display Modes Extension

extension LibraryView {
    // MARK: - Icons View (Grid)

    var iconsView: some View {
        GeometryReader { geometry in
            ScrollView {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 120, maximum: 150))],
                    alignment: .center,
                    spacing: 20
                ) {
                    ForEach(filteredDocuments) { doc in
                        DocumentThumbnailView(
                            document: doc,
                            isSelected: selection.contains(doc.id)
                        )
                        .draggable(doc.id)
                        .onTapGesture {
                            handleTap(doc)
                        }
                        .onTapGesture(count: 2) {
                            detailDocument = doc
                        }
                        .contextMenu {
                            documentContextMenu(for: doc)
                        }
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .onChange(of: geometry.size.width) { _, newWidth in
                // 120 min + 20 spacing = ~140 per column, minus padding
                let availableWidth = newWidth - 32  // account for .padding()
                gridColumnCount = max(1, Int(availableWidth / 140))
            }
            .onAppear {
                let availableWidth = geometry.size.width - 32
                gridColumnCount = max(1, Int(availableWidth / 140))
            }
        }
    }

    // MARK: - List View (Mail-style compact rows)

    var listView: some View {
        List {
            ForEach(filteredDocuments) { doc in
                MailStyleRow(document: doc, isSelected: selection.contains(doc.id))
                    .draggable(doc.id)
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
                    .onTapGesture(count: 2) {
                        handleTap(doc)
                        detailDocument = doc
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
        .listStyle(.plain)
    }

    // MARK: - Table View (Sortable columns)

    var tableView: some View {
        Table(filteredDocuments, selection: $selection, sortOrder: $sortOrder) {
            TableColumnForEach(visibleColumns) { col in
                TableColumn(col.title) { doc in
                    tableCellView(for: col.id, document: doc)
                }
                .width(min: col.minWidth, ideal: col.idealWidth)
            }
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
                detailDocument = doc
            }
        }
    }

    // MARK: - Map View (Tinderbox-style canvas)

    var mapView: some View {
        ScrollView([.horizontal, .vertical]) {
            ZStack(alignment: .topLeading) {
                // Grid background
                MapGridBackground()

                // Document cards
                ForEach(filteredDocuments) { doc in
                    MapCard(
                        document: doc,
                        isSelected: selection.contains(doc.id),
                        position: mapPositions[doc.id] ?? defaultMapPosition(for: doc)
                    )
                    .onTapGesture {
                        handleTap(doc)
                    }
                    .onTapGesture(count: 2) {
                        detailDocument = doc
                    }
                    .gesture(
                        DragGesture()
                            .onChanged { value in
                                mapPositions[doc.id] = value.location
                            }
                    )
                    .contextMenu {
                        documentContextMenu(for: doc)
                    }
                }
            }
            .frame(width: mapCanvasWidth, height: mapCanvasHeight)
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
