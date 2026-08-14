import SwiftUI

// MARK: - Calendar renderer (datasets Stage 2 — Daniel's addition)

/// A month grid over the date role. Day cells show their count from the
/// engine's day-granularity bins; selecting a day lists its rows below.
struct DatasetCalendarView: View {
    let store: DatasetModeStore
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

    /// "YYYY-MM" currently shown; seeded from the first binned month.
    @State private var month: String = ""
    @State private var selectedDay: String?

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
            ForEach(days, id: \.self) { day in
                dayCell(day, count: counts[day] ?? 0)
            }
        }
        .padding(10)
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
                VStack(spacing: 2) {
                    Text(String(Int(day.suffix(2)) ?? 0))
                        .font(.caption)
                        .monospacedDigit()
                    if count > 0 {
                        Text("\(count)")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.accentColor.opacity(0.2), in: Capsule())
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
            List(rowsOn(day: selectedDay)) { row in
                Text(row.name)
                    .contentShape(Rectangle())
                    .onTapGesture(count: 2) { onOpen(row) }
                    // Touch parity: iPad has no double-click.
                    .contextMenu { Button("Open") { onOpen(row) } }
            }
            .listStyle(.inset)
        } else {
            Text("Select a day with entries to list them here.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func rowsOn(day: String) -> [DatasetPage.Row] {
        guard let page = store.page, let dateAttr = store.attributeForRole["date"] else {
            return []
        }
        return page.rows.filter { store.text(dateAttr, of: $0)?.hasPrefix(day) == true }
    }
}
