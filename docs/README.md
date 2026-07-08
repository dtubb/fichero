(AI generated. Not reviewed.)

# Fichero Documentation

Fichero is a macOS document library for researchers: organize, read, annotate, and understand archival sources using AI workflows that stay on your computer.

This documentation is organized for two audiences.

---

## For users

Researchers, historians, archivists, and anyone using the Fichero app.

- [What Fichero Is](user/what-fichero-is.md) — philosophy, the three research layers (READ/THINK/WRITE), and the AI approach. Start here.
- [Install](user/install.md) — system requirements and first launch.
- [Getting Started](user/getting-started.md) — create a library, understand the main window.
- [Importing Documents](user/importing-documents.md) — link vs copy, drag and drop, supported file types.
- [Reading, Transcription, and Editing](user/reading-and-editing.md) — reading surfaces, extracted content, annotations, notes.
- [Search, Entities, and the Knowledge Graph](user/search-knowledge-graph.md) — semantic search, scoped queries, entity and claim inspection.
- [Curation, Notes, Annotations, and Workflows](user/curation-notes-workflows.md) — entity and claim curation, running workflows, activity.
- [AI, Models, and Privacy](user/ai-and-privacy.md) — local vs cloud models, what the AI does, data stays on your Mac, iPad access.
- [Tailscale Private Transport](./remote-backend-tailscale.md) — advanced tailnet-only remote engine setup; no public web surface.

Full user manual: [docs/user/README.md](user/README.md)

---

## For developers

Contributors and anyone building on or integrating with Fichero.

- [Developer Overview](developer/README.md) — the short developer entry point.
- [How Fichero Works](developer/how-fichero-works.md) — app ↔ engine runtime
  model, storage, workflows, KG extraction, and curation.
- [Architecture Overview](contributor/architecture-overview.md) — the two-part system: SwiftUI frontend + Python engine.
- [OpenAPI and Generated Clients](contributor/openapi-and-clients.md) — the contract path from Python to Swift.
- [Data Layer, Search, and Knowledge Graph Storage](contributor/data-search-and-kg.md) — DuckDB, LanceDB, entity writing.
- [Workflows, Activity, and Curation](contributor/workflows-activity-and-curation.md) — workflow execution, annotations API, curation.
- [Action Registry](contributor/action-registry.md) — the single audited write path for all mutations.
- [Security Model](contributor/security-model.md) — local binding, shared-secret token, multi-user ACL, Tailscale transport.
- [Tailscale Private Transport](./remote-backend-tailscale.md) — loopback-only engine plus `tailscale serve`, never Funnel or public bind.
- [Setup and Contributing](contributor/setup-and-contributing.md) — build commands, OpenAPI sync, contributing mechanics.

Full contributor index: [docs/contributor/README.md](contributor/README.md)

---

## Releases

- [Release Lane Runbook](./release/release-lane.md) — one-command DMG notarization,
  Sparkle/GitHub release, and Mac TestFlight upload.
- [Sparkle Release Setup](./release/sparkle-release.md) — app update metadata, feed URL, and release flow.

---

## Architecture deep-dives

Internal architecture docs for contributors working on specific subsystems:

- [docs/architecture/overview.md](./architecture/overview.md)
- [docs/architecture/action_layer.md](./architecture/action_layer.md)
- [docs/architecture/ai_infrastructure.md](./architecture/ai_infrastructure.md)
- [docs/architecture/image_editing_backend_strategy.md](./architecture/image_editing_backend_strategy.md)
- [docs/architecture/pi_agent_harness.md](./architecture/pi_agent_harness.md)
- [docs/architecture/mlx_on_device_agent.md](./architecture/mlx_on_device_agent.md)
- [docs/architecture/thinking-layer.md](./architecture/thinking-layer.md)
- [docs/architecture/swiftui/](./architecture/swiftui/)
- [docs/architecture/api/](./architecture/api/)

---

Fichero is made by Daniel Tubb and the [Tubb Lab](https://tubblab.com). Source: [github.com/dtubb/fichero](https://github.com/dtubb/fichero).
