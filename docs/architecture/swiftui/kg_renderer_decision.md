(AI generated. Not reviewed.)

# KG Renderer Decision

Date: 2026-05-31  
Issue: #1354

## Decision

Use `Cytoscape.js` hosted in the existing WebKit pane as the canonical KG graph renderer for inspector/library graph surfaces.

## Why

- Existing WebKit infrastructure is already in production for document KG views.
- Cytoscape.js supports the interactive graph behaviors we need (selection, filtering, layout updates, and larger node counts) without building a custom force engine in Swift.
- This keeps backend graph analytics (NetworkX/PyKEEN) separate from frontend rendering concerns.

## Rejected Alternatives

- GraphViz/SVG-only: good static rendering, insufficient interactivity for triage and curation workflows.
- Native custom force layout in Swift: high implementation and maintenance cost.
- RealityKit: wrong fit for 2D inspector graph workflows.

## Implementation Source Of Truth

- Swift enum: `KGGraphRendererFramework.selected == .cytoscapeWebKit`
- File: `fichero/fichero/Views/Library/DocumentKGSurface.swift`

All subsequent KG graph UI work should target this renderer unless superseded by a new architecture decision.
