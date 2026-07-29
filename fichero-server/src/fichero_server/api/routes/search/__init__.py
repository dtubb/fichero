"""fichero_server.api.routes.search package — search.py moved to search/core.py (#2569)."""
from fichero_server.api.routes.search.core import *  # noqa
# `import *` only re-exports public names; restore private symbols reached by
# tests directly (budget-neutral: core.py already loads for router registration).
from fichero_server.api.routes.search.core import (  # noqa: F401
    _apply_phrase_and_exclude_filters,
    _entity_match_results,
    _enrich_page_results_with_parent_info,
    _project_pdf_file_hits_to_pages,
    _run_content_search_sync,
    _suggest_for_no_results,
)
