"""API route modules."""

# Importing ANY route module must import fichero_server.api.main FIRST (#3950).
#
# main.py and the route modules are genuinely circular: main registers
# `activity.router`, while activity.py imports `get_library_database` from
# main. That resolves only in one order — main first, so its helpers exist by
# the time a route module asks for them.
#
# That ordering used to be provided ACCIDENTALLY by `fichero/api/__init__.py`
# doing `from fichero_server.api.main import app`: touching any leaf of fichero_server.api
# pulled main in eagerly and completely. #3950 had to make that lazy — the
# same eager import was the root of the fichero_server.db <-> api.main cycle
# (db -> db_manager -> api.change_stream -> api/__init__ -> api.main -> db),
# which made `import fichero_server.workflows.tools` impossible standalone.
#
# So the ordering moves HERE, where it is actually needed and where it costs
# nothing:
#   - `fichero_server.api.change_stream` (the db path) lives under fichero_server.api, NOT
#     under fichero_server.api.routes, so it no longer drags main in — cycle stays fixed.
#   - `fichero_server.cli.client` imports route modules directly for their response
#     types; it now gets main first, as it always silently did.
#   - When main itself imports a route, this re-entry is a no-op: main is
#     already in sys.modules and a plain `import` binds the partial module
#     without touching its attributes.
import fichero_server.api.main  # noqa: F401,E402  (import-order dependency, see above)

__all__ = [
    "actions_registry",
    "activity",
    "auth_accounts",
    "artifacts",
    "batch",
    "chat",
    "citation_rendering",
    "claim_curation",
    "claim_links",
    "claims",
    "documents",
    "entities",
    "folders",
    "hermeneutics",
    "ingest",
    "kg_curation_rules",
    "library_links",
    "library_items",
    "local_models",
    "locations",
    "mcp_servers",
    "mcp_tools",
    "migrations",
    "canvas",
    "model_comparison",
    "models",
    "multilingual",
    "orchestration",
    "providers",
    "research_agents",
    "schedules",
    "search",
    "search_explain",
    "settings",
    "sources",
    "storage",
    "tasks",
    "triggers",
    "workflow_execution",
    "workflows",
]
