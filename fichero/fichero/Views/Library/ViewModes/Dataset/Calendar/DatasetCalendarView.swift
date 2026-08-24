import SwiftUI

// MARK: - Calendar renderer (datasets Stage 2 — Daniel's addition)

/// A month grid over the date role. Day cells show their count from the
/// engine's day-granularity bins; selecting a day lists its rows below.
struct DatasetCalendarView: View {
    let store: DatasetModeStore
    /// Nil = read-only (previews, closed library); "Edit Date…" only
    /// appears when there is an engine to persist through.
    var entityService: EntityService?
    /// Shared with the shell (2026-08-16): a day-list click selects and the
    /// shell routes preview/reader/inspector; double-click still opens.
    @Binding var selection: Set<String>
    var onOpen: (DatasetPage.Row) -> Void = { _ in }
    var onOpenSource: (DatasetPage.Row) -> Void = { _ in }
    /// Nil = exclusion items hidden (previews, closed library).
    var documentService: DocumentService?
    var workflows: [WorkflowSidebarItem] = []
    var onRunWorkflow: (String, [String], String?, String?) -> Void = { _, _, _, _ in }

    /// "YYYY-MM" currently shown; seeded from the first binned month.
    @State private var month: String = ""
    @State private var selectedDay: String?
    @State private var editingRow: DatasetPage.Row?
    @State private var draftDate: String = ""

    var body: some View {
        if !store.hasDateSource {
            DatasetMissingRoleView(role: "date", renderer: "calendar")
        } else {
            VStack(spacing: 0) {
                monthHeader
                Divider()
                // The calendar IS the display (Daniel 2026-08-16: "you can
                // actually see it in the calendar … no need to show the
                // actual stuff below"): planner cells carry the entries'
                // words; clicking a day selects its entry, and the shell
                // routes preview/reader/inspector. The old below-the-grid
                // day list is retired with it.
                monthGrid
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            }
            .onAppear { seedMonth() }
            .onChange(of: store.page?.bins.first?.bin) { _, _ in seedMonth() }
            // "a nice calendar … that can be updated in place" (Daniel
            // 2026-08-14): the edit persists through the engine FIRST, then
            // the store moves just this row and re-bins locally.
            .alert(
                "Edit Date",
                isPresented: Binding(
                    get: { editingRow != nil },
                    set: { if !$0 { editingRow = nil } }
                ),
                presenting: editingRow
            ) { row in
                TextField("YYYY-MM-DD", text: $draftDate)
                Button("Save") {
                    let value = draftDate.trimmingCharacters(in: .whitespaces)
                    guard let entityService, let dateAttr = store.attributeForRole["date"],
                          !value.isEmpty else { return }
                    Task { await store.saveAttribute(dateAttr, value: value, on: row, entityService: entityService) }
                }
                Button("Cancel", role: .cancel) {}
            } message: { row in
                Text("The “date” attribute of \(row.name).")
            }
        }
    }

    /// Counts per day ("YYYY-MM-DD") from the engine bins.
    private var countsByDay: [String: Int] {
        Dictionary(
            (store.page?.bins ?? []).map { ($0.bin, $0.count) },
            uniquingKeysWith: +
        )
    }

    private var availableMonths: [String] {
        Array(Set((store.page?.bins ?? []).map { String($0.bin.prefix(7)) })).sorted()
    }

    private func seedMonth() {
        if month.isEmpty || !availableMonths.contains(month) {
            month = availableMonths.first ?? ""
        }
    }

    private var monthHeader: some View {
        HStack {
            Button {
                step(-1)
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.borderless)
            .disabled(availableMonths.first == month)
            .accessibilityLabel("Previous month")
            Spacer(minLength: 0)
            Text(monthTitle)
                .font(.headline)
            Spacer(minLength: 0)
            Button {
                step(1)
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.borderless)
            .disabled(availableMonths.last == month)
            .accessibilityLabel("Next month")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    private var monthTitle: String {
        let pieces = month.split(separator: "-")
        guard pieces.count == 2, let monthNumber = Int(pieces[1]),
              (1...12).contains(monthNumber) else { return month }
        return "\(Calendar.current.monthSymbols[monthNumber - 1]) \(pieces[0])"
    }

    private func step(_ direction: Int) {
        guard let index = availableMonths.firstIndex(of: month) else { return }
        let next = index + direction
        guard availableMonths.indices.contains(next) else { return }
        month = availableMonths[next]
        selectedDay = nil
    }

    private var monthGrid: some View {
        let days = daysInShownMonth
        let counts = countsByDay
        // Planner geometry: the month's week-rows split the pane height, so
        // cells GROW with the window ("why can't it be even bigger").
        let weekRows = max(1, Int(ceil(Double(days.count) / 7)))
        return GeometryReader { geo in
        LazyVGrid(
            columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 7),
            spacing: 4
        ) {
            // id by POSITION here too: "S" and "T" each appear twice in the
            // week, and duplicate \.self ids DROP the repeats (the rendered
            // header read "S M T W · F ·" until the preview caught it).
            ForEach(Array(weekdayHeaders.enumerated()), id: \.offset) { _, symbol in
                Text(symbol)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            // id by POSITION: the leading blanks are all "" and duplicate
            // \.self ids corrupt ForEach diffing.
            ForEach(Array(days.enumerated()), id: \.offset) { _, day in
                dayCell(
                    day, count: counts[day] ?? 0,
                    height: max(44, (geo.size.height - 40) / CGFloat(weekRows) - 4)
                )
            }
        }
        .padding(10)
        }
    }

    /// Weekday column headers, rotated to the user's first weekday.
    private var weekdayHeaders: [String] {
        let symbols = Calendar.current.veryShortWeekdaySymbols
        let first = Calendar.current.firstWeekday - 1
        return Array(symbols[first...] + symbols[..<first])
    }

    /// "YYYY-MM-DD" for every day of the shown month, padded so day 1 lands
    /// on its weekday column (leading blanks are empty strings).
    private var daysInShownMonth: [String] {
        let pieces = month.split(separator: "-")
        guard pieces.count == 2, let year = Int(pieces[0]), let monthNumber = Int(pieces[1]),
              let firstDay = DateComponents(
                calendar: .current, year: year, month: monthNumber, day: 1
              ).date,
              let range = Calendar.current.range(of: .day, in: .month, for: firstDay)
        else { return [] }
        let leadingBlanks = (Calendar.current.component(.weekday, from: firstDay)
            - Calendar.current.firstWeekday + 7) % 7
        let blanks = (0..<leadingBlanks).map { _ in "" }
        let days = range.map { String(format: "%04d-%02d-%02d", year, monthNumber, $0) }
        return blanks + days
    }

    @ViewBuilder
    private func dayCell(_ day: String, count: Int, height: CGFloat) -> some View {
        if day.isEmpty {
            Color.clear.frame(height: height)
        } else {
            let rows = count > 0 ? rowsOn(day: day) : []
            let isSelected = rows.contains { selection.contains($0.id) }
            Button {
                selectedDay = day
                // A day click IS a selection: the first entry of the day
                // routes preview (source page + bbox), reader and inspector
                // through the shell's router — same grammar as every other
                // renderer.
                if let first = rows.first {
                    selection = SelectionGrammar.select(first.id).selection
                }
            } label: {
                dayCellLabel(
                    day, count: count, rows: rows,
                    height: height, highlighted: isSelected || selectedDay == day
                )
            }
            .buttonStyle(.plain)
            .disabled(count == 0)
            .contextMenu { dayCellMenu(rows) }
        }
    }

    private func dayCellLabel(
        _ day: String, count: Int, rows: [DatasetPage.Row],
        height: CGFloat, highlighted: Bool
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
                Text(String(Int(day.suffix(2)) ?? 0))
                    .font(.caption.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(count > 0 ? .primary : .tertiary)
                Spacer(minLength: 0)
                if count > 1 {
                    Text("\(count)")
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.accentColor.opacity(0.2), in: Capsule())
                }
            }
            // The day's words, in the day's square — the calendar is
            // the reading surface, not a navigator to one.
            if let first = rows.first,
               let words = store.displayExcerpt(of: first) {
                Text(words)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(store.textDetail == .full ? nil : 4)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Spacer(minLength: 0)
        }
        .padding(5)
        .frame(maxWidth: .infinity, minHeight: height, alignment: .topLeading)
        .background(
            highlighted ? Color.accentColor.opacity(0.15) : Color.clear,
            in: RoundedRectangle(cornerRadius: 6)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.primary.opacity(0.06))
        )
    }

    @ViewBuilder
    /// The ONE dataset row menu — a day cell targets the day's rows, so the
    /// batch a verb applies to is the whole cell rather than one entry.
    private func dayCellMenu(_ rows: [DatasetPage.Row]) -> some View {
        DatasetRowMenu(
            rows: rows,
            targets: cellTargets(rows),
            canEditDate: entityService != nil && store.attributeForRole["date"] != nil,
            documentService: documentService,
            workflows: workflows,
            onOpen: onOpen,
            onOpenSource: onOpenSource,
            onEditDate: { row in
                draftDate = store.dateValue(of: row) ?? ""
                editingRow = row
            },
            onRunWorkflow: onRunWorkflow
        )
    }

    /// The Finder rule for a day cell: if the click lands inside the current
    /// selection the batch IS the selection, else it is the day.
    private func cellTargets(_ rows: [DatasetPage.Row]) -> [String] {
        let ids = rows.map(\.id)
        return ids.contains(where: selection.contains) ? Array(selection) : ids
    }
}

// Pure helpers, split from the struct body at the 250-line lint budget
// (2026-08-16, the shared-selection rows tipped it) — same members.
private extension DatasetCalendarView {

    /// "January 4, 1942" from "1942-01-04"; falls back to the raw string.
    func dayTitle(_ day: String) -> String {
        let pieces = day.split(separator: "-")
        guard pieces.count == 3, let monthNumber = Int(pieces[1]),
              (1...12).contains(monthNumber), let dayNumber = Int(pieces[2])
        else { return day }
        return "\(Calendar.current.monthSymbols[monthNumber - 1]) \(dayNumber), \(pieces[0])"
    }

    func rowsOn(day: String) -> [DatasetPage.Row] {
        guard store.page != nil, store.hasDateSource else {
            return []
        }
        return store.visibleRows.filter { store.dateValue(of: $0)?.hasPrefix(day) == true }
    }
}

#Preview("Calendar — diary") {
    DatasetCalendarView(store: .previewDiary(), selection: .constant([]))
        .frame(width: 720, height: 640)
}
