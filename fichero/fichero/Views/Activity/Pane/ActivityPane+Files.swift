//
//  ActivityPane+Files.swift
//  Fichero
//
//  A run's FILE rows, split from ActivityPane.swift for length (`activity.pane.one-outline-table`, #6441): one row per
//  document among the run's page nodes, a multi-page file once with its pages under it.
//

import Foundation

extension ActivityPane {
    /// A run's FILES: one row per distinct document among the page nodes of its tree, in the tree's order; its state the
    /// worst of its pages', its counts its pages; nil when the tree names no document (no disclosure). The pages of a
    /// multi-page file (the engine's `file_id`) are ONE file row, the pages under it (`multiPageFileRow`).
    static func files(of row: ActivityMonitorRow) -> [ActivityMonitorRow]? {
        var order: [String] = []
        var pages: [String: [ActivityMonitorRow]] = [:]
        for page in leaves(of: row) {
            guard let documentId = page.documentId else { continue }
            let file = page.fileId ?? documentId
            if pages[file] == nil { order.append(file) }
            pages[file, default: []].append(page)
        }
        guard !order.isEmpty else { return nil }
        return order.map { file in
            let id = "\(row.id)|file:\(file)"
            let nodes = pages[file] ?? []
            guard nodes.contains(where: { $0.fileId != nil }) else {
                return fileRow(id: id, documentId: file, pages: nodes, parent: row)
            }
            return multiPageFileRow(id: id, fileId: file, nodes: nodes, parent: row)
        }
    }

    /// A multi-page file's row: named by the file, its count its pages, its state the worst of theirs; under it one row
    /// per page (the worst of that page's runs, a failed page's reason on its row), in the tree's order.
    private static func multiPageFileRow(id: String, fileId: String, nodes: [ActivityMonitorRow],
                                         parent: ActivityMonitorRow) -> ActivityMonitorRow {
        var order: [String] = []
        var runs: [String: [ActivityMonitorRow]] = [:]
        for node in nodes {
            guard let page = node.documentId else { continue }
            if runs[page] == nil { order.append(page) }
            runs[page, default: []].append(node)
        }
        let pageRows = order.map { page in
            fileRow(id: "\(id)|page:\(page)", documentId: page, pages: runs[page] ?? [], parent: parent)
        }
        var row = fileRow(id: id, documentId: fileId, pages: pageRows, parent: parent)
        if let name = nodes.lazy.compactMap(\.fileName).first { row.name = name }
        row.children = pageRows
        return row
    }

    static func fileRow(id: String, documentId: String, pages: [ActivityMonitorRow],
                        parent: ActivityMonitorRow) -> ActivityMonitorRow {
        let first = pages.first
        var row = ActivityMonitorRow(
            id: id, kind: .page, libraryId: parent.libraryId, runRowID: parent.runRowID, runThreadId: parent.runThreadId,
            jobId: first?.jobId, name: first?.name ?? documentId, projectName: nil,
            phase: worst(pages.map(\.phase)), reason: pages.first { $0.phase == .failed }?.reason, workingOn: nil,
            done: pages.filter { $0.phase == .done }.count, total: pages.count,
            started: pages.compactMap(\.started).min(), seconds: sum(pages.compactMap(\.seconds)),
            costUsd: sum(pages.compactMap(\.costUsd)), tokens: pages.map(\.tokens).reduce(0, +),
            errors: pages.filter { $0.phase == .failed }.count, model: first?.model, isLive: false, children: nil
        )
        row.documentId = documentId
        row.engineKind = first?.engineKind
        row.ended = pages.compactMap(\.ended).max()
        return row
    }

    private static func sum(_ values: [Double]) -> Double? { values.isEmpty ? nil : values.reduce(0, +) }
}
