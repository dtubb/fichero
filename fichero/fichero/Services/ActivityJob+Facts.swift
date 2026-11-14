//
//  ActivityJob+Facts.swift
//  Fichero
//
//  What a row says beyond its state (`activity.pane.row-says-what-ran-on-what`, `activity.pane.failure-with-its-fix-in-the-row`,
//  #6441, #6354): its stages, what it ran on, and its failure with the fix, as the engine's list row carries them.
//

import Foundation

extension ActivityJob {
    struct Failure: Equatable {
        let kind: String
        let words: String
        let fix: String
        /// The actions' kinds in the order to offer them: resume, retry, open-settings, choose-model, report-bug, reconnect.
        let actions: [String]
        var primaryAction: String? { actions.first }
    }

    /// One of a recipe run's stages, as the engine counts it: Set Up's order, its state and its pages.
    struct Stage: Equatable {
        let title: String
        let state: String
        let done: Int
        let total: Int
    }

    struct RanOn: Equatable {
        let kind: String
        let count: Int
        let name: String?
    }
}
