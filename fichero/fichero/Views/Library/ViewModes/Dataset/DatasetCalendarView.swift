import SwiftUI

// MARK: - Calendar renderer (datasets Stage 2 — Daniel's addition)

/// A month grid over the date role. Day cells show their count from the
/// engine's day-granularity bins; selecting a day lists its rows below.
struct DatasetCalendarView: View {
    let store: DatasetModeStore
    /// Nil = read-only (previews, closed library); "Edit Date…" only
    /// appears when there is an engine to persist through.
    var entityService: EntityService?
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

    /// "YYYY-MM" currently shown; seeded from the first binned month.
    @State private var month: String = ""
    @State private var selectedDay: String?
    @State private var editingRow: DatasetPage.Row?
    @State private var draftDate: String = ""

    var body: some View {
        if store.attributeForRole["date"] == nil {
            DatasetMissingRoleView(role: "date", renderer: "calendar")
        } else {
            VStack(spacing: 0) {
                monthHeader
                Divider()
                monthGrid
                Divider()
                dayList
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
        return LazyVGrid(
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
                dayCell(day, count: counts[day] ?? 0)
            }
        }
        .padding(10)
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
    private func dayCell(_ day: String, count: Int) -> some View {
        if day.isEmpty {
            Color.clear.frame(height: 44)
        } else {
            Button {
                selectedDay = (selectedDay == day) ? nil : day
            } label: {
                VStack(spacing: 3) {
                    Text(String(Int(day.suffix(2)) ?? 0))
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(count > 0 ? .primary : .secondary)
                    // One entry = a quiet dot; several = the count. A diary
                    // is mostly one entry per day, and a wall of "1" chips
                    // reads as noise (preview-driven, 2026-08-14).
                    if count > 1 {
                        Text("\(count)")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.accentColor.opacity(0.2), in: Capsule())
                    } else if count == 1 {
                        Circle()
                            .fill(Color.accentColor)
                            .frame(width: 5, height: 5)
                            .padding(.vertical, 3)
                    } else {
                        Text(" ").font(.caption2)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(
                    selectedDay == day ? Color.accentColor.opacity(0.15) : Color.clear,
                    in: RoundedRectangle(cornerRadius: 6)
                )
            }
            .buttonStyle(.plain)
            .disabled(count == 0)
        }
    }

    @ViewBuilder
    private var dayList: some View {
        if let selectedDay {
            let rows = rowsOn(day: selectedDay)
            VStack(alignment: .leading, spacing: 0) {
                Text("\(dayTitle(selectedDay)) — \(rows.count) \(rows.count == 1 ? "entry" : "entries")")
                    .font(.subheadline.weight(.semibold))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                // ScrollView, not List — same reasoning as the timeline
                // (no selection model; List asserted under the preview
                // host).
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(rows) { row in
                            dayListRow(row)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 5)
                                .contentShape(Rectangle())
                                .onTapGesture(count: 2) { onOpen(row) }
                                // Touch parity: iPad has no double-click.
                                .contextMenu {
                                    Button("Open") { onOpen(row) }
                                    if entityService != nil, let dateAttr = store.attributeForRole["date"] {
                                        Button("Edit Date…") {
                                            draftDate = store.text(dateAttr, of: row) ?? ""
                                            editingRow = row
                                        }
                                    }
                                }
                            Divider().padding(.leading, 16)
                        }
                    }
                }
            }
        } else {
            Text("Select a day with entries to list them here.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// Name plus the title role (the place, for a diary) when it adds
    /// something beyond the name.
    private func dayListRow(_ row: DatasetPage.Row) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(row.name)
                    .lineLimit(1)
                if let titleAttr = store.attributeForRole["title"],
                   let title = store.text(titleAttr, of: row), title != row.name {
                    Text(title)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            // The day's words, right where the day was picked.
            if let excerpt = row.excerpt {
                Text(excerpt)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
    }

    /// "January 4, 1942" from "1942-01-04"; falls back to the raw string.
    private func dayTitle(_ day: String) -> String {
        let pieces = day.split(separator: "-")
        guard pieces.count == 3, let monthNumber = Int(pieces[1]),
              (1...12).contains(monthNumber), let dayNumber = Int(pieces[2])
        else { return day }
        return "\(Calendar.current.monthSymbols[monthNumber - 1]) \(dayNumber), \(pieces[0])"
    }

    private func rowsOn(day: String) -> [DatasetPage.Row] {
        guard let page = store.page, let dateAttr = store.attributeForRole["date"] else {
            return []
        }
        return page.rows.filter { store.text(dateAttr, of: $0)?.hasPrefix(day) == true }
    }
}

#Preview("Calendar — diary") {
    DatasetCalendarView(store: .previewDiary())
        .frame(width: 720, height: 640)
}
