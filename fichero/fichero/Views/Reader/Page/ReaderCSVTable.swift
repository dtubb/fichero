import Foundation

// MARK: - CSV as a real table in the Reader (Daniel, 2026-09-04)
//
// "Will a reader show csv? Should our reader have a csv option, to render it
// properly?" Yes. A table artifact reached the reader as its raw comma-
// separated bytes — a wall of commas is not a reading of a ledger.
//
// Pure: parsing and rendering are separable from the pane, which is what
// makes "malformed CSV falls back to plain text" a testable promise rather
// than a hope. The renderer NEVER invents structure: a row with the wrong
// number of fields is a parse failure, and a parse failure shows the text.

/// RFC 4180-shaped CSV, reduced to what a table needs.
enum ReaderCSVTable {

    /// Beyond this many rows the table stops being a reading and starts being
    /// a scroll. The rest are not hidden — the caption says how many were
    /// left, and the CSV is still exportable from the head's chip.
    static let maxRows = 500

    /// Parse `text` into rows of fields.
    ///
    /// Returns `nil` — never a partial table — when the text is not honest
    /// CSV: no rows, a single column throughout (that is prose, not a table),
    /// or ragged rows. A table drawn from ragged rows silently shifts values
    /// into the wrong columns, which for a ledger is a wrong number under the
    /// right heading.
    static func parse(_ text: String, separator: Character = ",") -> [[String]]? {
        var rows: [[String]] = []
        var field = ""
        var row: [String] = []
        var inQuotes = false
        var iterator = text.makeIterator()
        var pending: Character?

        func endField() {
            row.append(field)
            field = ""
        }
        func endRow() {
            endField()
            // A trailing newline yields one empty field; that is not a row.
            if !(row.count == 1 && row[0].isEmpty) { rows.append(row) }
            row = []
        }

        while let character = pending ?? iterator.next() {
            pending = nil
            if inQuotes {
                if character == "\"" {
                    // "" inside a quoted field is a literal quote.
                    if let next = iterator.next() {
                        if next == "\"" {
                            field.append("\"")
                        } else {
                            inQuotes = false
                            pending = next
                        }
                    } else {
                        inQuotes = false
                    }
                } else {
                    field.append(character)
                }
                continue
            }
            switch character {
            case "\"" where field.isEmpty:
                inQuotes = true
            case separator:
                endField()
            case "\r":
                continue
            case "\n":
                endRow()
            default:
                field.append(character)
            }
        }
        if inQuotes { return nil }   // an unterminated quote is malformed
        if !field.isEmpty || !row.isEmpty { endRow() }

        guard let width = rows.first?.count, width > 1 else { return nil }
        guard rows.allSatisfy({ $0.count == width }) else { return nil }
        return rows
    }

    /// The rendered table, or `nil` when the text is not a table — the caller
    /// then shows the text, which is always true even when it is ugly.
    ///
    /// The first row is treated as the header: every CSV this app produces
    /// writes one, and a table with no header row still reads correctly with
    /// its first line emphasised.
    static func html(_ text: String, title: String? = nil) -> String? {
        guard let rows = parse(text), let header = rows.first else { return nil }
        let body = rows.dropFirst()
        let shown = body.prefix(maxRows)
        var markup = ""
        if let title, !title.isEmpty {
            markup += "<h1>\(ReaderArtifactDiff.escape(title))</h1>"
        }
        markup += "<table><thead><tr>"
        markup += header.map { "<th>\(ReaderArtifactDiff.escape($0))</th>" }.joined()
        markup += "</tr></thead><tbody>"
        for row in shown {
            markup += "<tr>"
            markup += row.map { "<td>\(ReaderArtifactDiff.escape($0))</td>" }.joined()
            markup += "</tr>"
        }
        markup += "</tbody></table>"
        if body.count > shown.count {
            markup += """
            <p class="truncated">Showing the first \(shown.count) of \
            \(body.count) rows. Save the CSV from the head to read them all.</p>
            """
        }
        return page(body: markup)
    }

    /// The table's own document shell. Shares the diff lens's rules — system
    /// fonts, both appearances declared, a body the host paints — and adds
    /// what a table needs: a sticky header and its own horizontal scroll, so
    /// a wide ledger scrolls inside the table rather than the pane.
    static func page(body: String) -> String {
        """
        <!DOCTYPE html>
        <html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
        :root { color-scheme: light dark; }
        body {
          font: -apple-system-body;
          font-family: -apple-system, system-ui, sans-serif;
          margin: 0; padding: 16px; overflow-x: auto;
        }
        h1 { font-size: 1.1em; margin: 0 0 12px; }
        table { border-collapse: collapse; width: 100%; }
        th, td {
          text-align: left; padding: 4px 10px; vertical-align: top;
          border-bottom: 1px solid color-mix(in srgb, currentColor 12%, transparent);
        }
        th {
          position: sticky; top: 0;
          background: Canvas;
          border-bottom-width: 2px;
        }
        tbody tr:hover { background: color-mix(in srgb, currentColor 6%, transparent); }
        .truncated { color: color-mix(in srgb, currentColor 55%, transparent); font-size: 0.9em; }
        </style></head>
        <body>\(body)</body></html>
        """
    }
}
