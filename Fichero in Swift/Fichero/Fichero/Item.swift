//
//  Item.swift
//  Fichero
//
//  Created by Daniel Tubb on 2025-12-11.
//

import Foundation
import SwiftData

@Model
final class Item {
    var timestamp: Date
    
    init(timestamp: Date) {
        self.timestamp = timestamp
    }
}
