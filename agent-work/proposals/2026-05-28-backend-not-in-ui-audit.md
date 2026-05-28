# Backend API Routes Not Yet Visible in SwiftUI

Date: 2026-05-28  
Issue: #1288  
Scope: read-only audit of `fichero-engine/src/fichero/api/main.py`, route modules, and Swift callers under `fichero/fichero/`.

## Summary

The backend has two kinds of hidden work:

1. **No Swift caller at all**: the route group exists in FastAPI, but no Swift service/view calls it.
2. **Swift caller exists, but the surface is hidden or service-only**: usually behind `FeatureManager` flags or present only as a service wrapper with no clear default navigation.

Highest-value no-caller or service-only features to surface first:

1. **Notes/backlinks + projects**: release-tier backend, no app-level Swift caller. This is the most direct way to make Fichero feel like a research workspace instead of only a document browser.
2. **Bibliography import/export/extract**: release-tier backend and partial Swift service wrappers exist, but no obvious user-facing document metadata/bibliography workflow.
3. **KG review/triangulation/mutations/rendering**: release-tier backend with high-value KG cleanup and explanation tools, but most are backend-only while the Ontology UI already exists.

Gated-but-wired features that are not "no caller" but still hidden by default: chat/model comparison, integrations, automation schedules/triggers, MCP server management, local models, mind palace, actions, and batches.

## Route Group Coverage

`Y` means at least one Swift service/view calls the backend group. `N` means no Swift caller was found under `fichero/fichero/`.

| Endpoint group | Backend file | Swift caller? | What UI surface would expose it | Tier |
|---|---|---:|---|---|
| `/api/activity` | `activity.py` | Y | Activity sidebar/detail | release |
| `/api/annotations` | `annotations.py` | Y | Document Inspector annotations + image editor | release |
| `/api/notes` | `notes.py` | N | Notes/backlinks pane on document, project, and entity inspectors | release |
| `/api/projects` | `projects.py` | N | Project/workspace browser for grouped docs, notes, and research outputs | release |
| `/api/artifacts` | `artifacts.py` | Y | Inspector artifacts tab + artifacts browser | release |
| `/api/bibliography` | `bibliography.py` | Y | Service wrapper exists; expose in Document Inspector metadata/bibliography tab | release |
| `/api/batches` | `batch.py` | Y | Batch queue/monitor; currently feature-gated/service-driven | release |
| `/api/chat` | `chat.py` | Y | Chat view; hidden by `chat` feature flag | release |
| `/api/citations/graph` | `citations.py` | Y | Document Inspector citation graph read panes | release |
| `/api/citations/*render/export*` | `citation_rendering.py` | N | Citation export/download action from document/library menus | release |
| `/api/classifications` | `classifications.py` | N | Classification result review or document metadata panel | release |
| `/api/claim-links` | `claim_links.py` | Y | Claim related/supports/contradicts UI in KG inspector | release |
| `/api/claims` | `claims.py`, `claim_curation.py` | Y | Ontology browser, document inspector claims, curation states | release |
| `/api/documents` | `documents.py`, `document_inspector.py` | Y | Library, sidebar, inspector, import | release |
| `/api/entities` | `entities.py`, `entity_inspector.py` | Y | Ontology browser + entity detail | release |
| `/api/export` | `export.py` | N | Library/document export menu | release |
| `/api/folders/{entity_type}` | `folders.py` | N | Entity-folder organizer, if still desired; otherwise likely legacy | release |
| `/api/ingest` | `ingest.py` | Y | File/folder import; XLSX import still needs an obvious UI affordance | release |
| `/api/images` | `image_editing.py` | Y | Image editor operations | release |
| `/api/library` | `library.py` | N | New/open library package wizard or diagnostics | release |
| `/api/registry` | `library_registry.py` | N | Known libraries picker/manager | release |
| `/api/libraries/{lib}/entity-types` | `library_entity_types.py` | N | Ontology/entity-type settings | release |
| `/api/migrations` | `migrations.py` | N | Admin-only migration diagnostics; probably keep hidden | release |
| `/api/mcp/tools` | `mcp_tools.py` | N | MCP/thin-tool diagnostics, not normal UI | release |
| `/api/multilingual` | `multilingual.py` | N | Multilingual normalization/search settings or entity tools | release |
| `/api/providers` | `providers.py` | Y | Provider/model settings | release |
| `/api/registries` | `registries.py` | N | Claim vocabulary settings for epistemic statuses/claim kinds | release |
| `/api/references` | `references.py` | N | References browser, or merge into bibliography UI | release |
| `/api/search` | `search.py` | Y | Search view, saved searches, keyword cloud/stats | release |
| `/api/search/views/*` | `search.py` | N | Backend-shaped table/map/grid search result modes per #1072 | release |
| `/api/settings` | `settings.py` | Y | Settings tabs and AI defaults | release |
| `/api/sources` | `sources.py` | N | Source/reference browser, unless superseded by bibliography/research | release |
| `/api/storage` | `storage.py` | Y | Images, thumbnails, Quick Look/source viewing | release |
| `/api/storage/stats`, `/debug`, `/snapshots` | `storage.py` | N | Backend diagnostics/library backup tools | release |
| `/api/tasks` | `tasks.py` | N | Task/progress diagnostics, likely Activity-adjacent | release |
| `/api/workflow-execution` | `workflow_execution/` | Y | Workflow run/status/stream UI | release |
| `/api/workflows` | `workflows.py` | Y | Workflow list/editor/tools | release |
| `/view/document` | `views.py` | Y | Document web/KG panes | release |
| `/api/kg/rebuild` | `kg_rebuild.py` | N | KG repair/reindex action in advanced Ontology tools | release |
| `/api/kg/triangulation` | `kg_triangulation.py` | N | Entity/claim corroboration panel | release |
| `/api/kg/graph` | `kg_graph.py` | Y | Neighborhood has a caller; centrality/path/community/etc. remain hidden | release |
| `/api/kg/render` | `kg_render.py` | N | "Draft paragraph/explanation" action from entity/claim views | release |
| `/api/kg/pykeen` | `kg_pykeen.py` | N | ML prediction/training diagnostics; keep hidden unless explicitly approved | release |
| `/api/kg/predictions` | `kg_predictions.py` | Y | Heuristic prediction service exists; apply/review flow still unclear | release |
| `/api/kg/review` | `kg_review.py` | N | Entity-match review queue in Ontology browser | release |
| `/api/kg/mutations` | `kg_mutations.py` | N | KG audit/undo history panel | release |
| `/api/kg/claim-search` | `kg_claim_search.py` | Y | Similar claims and embedding actions | release |
| `/api/kg/claim-analysis` | `kg_claim_analysis.py` | Y | Contradictions/evidence-chain claim detail tools | release |
| `/api/kg/entity-curation` | `kg_entity_curation.py` | Y | Ontology merge/split/audit/semantic tools | release |
| `/api/kg/sparql` | `kg_sparql.py` | N | Advanced SPARQL console; likely keep hidden | release |
| `/api/kg/inclusion` | `kg_inclusion.py` | N | KG inclusion/scope controls, maybe project/library settings | release |
| `/api/hermeneutics`, `/api/kg/interpretations` | `hermeneutics.py` | N | Interpretive reading layer on top of entities/claims | release |
| `/api/chains` | `chains.py` | Y | Workflow chains list/editor | release |
| `/api/search/explain` | `search_explain.py` | N | "Why this result?" search inspector | dev |
| `/api/mind-palace` | `mind_palace.py` | Y | Mind Palace spatial workspace; currently feature-gated | dev |
| `/api/research` | `research_agents.py` + subrouters | Y | Research workspace; currently visible via Research mode | dev |
| `/api/iiif` | `iiif.py` | N | IIIF manifest/image interoperability surface | dev |
| `/api/actions` | `actions.py` | Y | Action library/picker; feature-gated | dev |
| `/api/integrations` | `integrations.py` | Y | Integrations view; feature-gated | dev |
| `/api/local-models` | `local_models.py` | Y | Models settings tab; feature-gated/settings-only | dev |
| `/api/mcp-servers` | `mcp_servers.py` | Y | MCP server management screens; feature-gated | dev |
| `/api/orchestration`, `/api/agents/write` | `orchestration.py` | N | Agent-write policy/approval diagnostics; keep gated | dev |
| `/api/schedules` | `schedules.py` | Y | Automation schedule editor/detail; feature-gated | dev |
| `/api/triggers` | `triggers.py` | Y | Automation trigger editor/detail; feature-gated | dev |

## Backend Groups With No Swift Caller

These are the true "built but not called from SwiftUI" groups found in this pass:

- Release: notes, projects, citation rendering/export, classifications, export, folders, library, library registry, library entity types, migrations, MCP tool endpoints, multilingual, registries, references, search backend views, sources, storage stats/debug/snapshots, tasks, KG rebuild, KG triangulation, KG render, KG PyKEEN, KG review, KG mutations, KG SPARQL, KG inclusion, hermeneutics/interpretations.
- Dev: search explain, IIIF, orchestration/agent-write policy.

## Enable First

1. **Notes/backlinks and projects**: add a simple Notes/Backlinks section to Document Inspector and a Projects sidebar workspace. This exposes release-tier backend features with low security risk.
2. **Bibliography and citation export**: wire existing bibliography service calls plus citation rendering/export into Document Inspector metadata and library/document menus.
3. **KG cleanup/review tools**: surface KG review, mutations/audit undo, triangulation, and render paragraph actions inside the existing Ontology browser before adding new experimental UI.

Keep these gated until explicit approval: MCP server management, orchestration/agent-write policy, PyKEEN training, SPARQL console, IIIF, and external integrations if #1151 classifies them as risky.
