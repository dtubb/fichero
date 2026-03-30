import SwiftUI

// MARK: - Display Modes Extension

extension LibraryView {
    // MARK: - Icons View (Grid)

    var iconsView: some View {
        let itemMin = CGFloat(max(60, 120 * iconViewScale))
        let itemMax = CGFloat(max(80, 150 * iconViewScale))
        return GeometryReader { geometry in
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
                                isSelected: selection.contains(doc.id)
                            )
                            .id(doc.id)
                            .draggable(doc.id)
                            .onTapGesture(count: 2) {
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
                .focusable()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .onChange(of: geometry.size.width) { _, newWidth in
                    let cellWidth = CGFloat(120 * iconViewScale) + 20
                    let availableWidth = newWidth - 32
                    gridColumnCount = max(1, Int(availableWidth / cellWidth))
                }
                .onAppear {
                    let cellWidth = CGFloat(120 * iconViewScale) + 20
                    let availableWidth = geometry.size.width - 32
                    gridColumnCount = max(1, Int(availableWidth / cellWidth))
                }
                .onChange(of: listScrollTarget) { _, id in
                    guard let id else { return }
                    withAnimation {
                        proxy.scrollTo(id, anchor: .center)
                    }
                    listScrollTarget = nil
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
                        MailStyleRow(document: doc, isSelected: selection.contains(doc.id)) { tag in
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
                            detailDocument = doc
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
        }
    }

    // MARK: - Table View (Sortable columns)

    var tableView: some View {
        Table(filteredDocuments, selection: $selection, sortOrder: $sortOrder) {
            if showName {
                TableColumn("Name", value: \Document.name) { doc in
                    tableCellView(for: "name", document: doc)
                }
                .width(min: 150, ideal: 200)
            }
            if showStatus {
                TableColumn("Status", value: \Document.status.rawValue) { doc in
                    tableCellView(for: "status", document: doc)
                }
                .width(min: 80, ideal: 100)
            }
            if showProgress {
                TableColumn("Progress") { doc in
                    tableCellView(for: "progress", document: doc)
                }
                .width(min: 80, ideal: 100)
            }
            if showOutput {
                TableColumn("Output") { doc in
                    tableCellView(for: "output", document: doc)
                }
                .width(min: 150, ideal: 250)
            }
            if showFileType {
                TableColumn("Type", value: \Document.sortableFileType) { doc in
                    tableCellView(for: "fileType", document: doc)
                }
                .width(min: 60, ideal: 80)
            }
            if showPath {
                TableColumn("Path") { doc in
                    tableCellView(for: "path", document: doc)
                }
                .width(min: 100, ideal: 150)
            }
            if showCreatedDate {
                TableColumn("Created", value: \Document.createdAt) { doc in
                    tableCellView(for: "createdDate", document: doc)
                }
                .width(min: 80, ideal: 100)
            }
            if showModifiedDate {
                TableColumn("Modified", value: \Document.updatedAt) { doc in
                    tableCellView(for: "modifiedDate", document: doc)
                }
                .width(min: 80, ideal: 100)
            }
            if showSize {
                TableColumn("Size") { doc in
                    tableCellView(for: "size", document: doc)
                }
                .width(min: 60, ideal: 80)
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
                        detailDocument = doc
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
