"""What each registered workflow tool writes, and where it attaches (#5596).

`source.extract.every-output-declares-its-anchor` (spec: `source/source-model.md`, "Extracted
data, integrated"): every registered tool declares which record kinds it writes and the finest
level of the archive its output attaches to. `scripts/check_tool_outputs_declared.py` fails a
registered tool with no declaration here, and a tool that writes only a document artifact unless
it is a known gap naming the slice issue that moves its output onto the page.

Each entry was filled from what the tool's code does on 2026-10-08, not from what it should do:
a tool that saves an artifact says ``artifact`` even where the review says that is the wrong home.

``writes`` vocabulary (the record kinds of the review's target, plus what the code has today):

- ``pass``       a pass of segments (boxes become segment rows, `convert_new_results`)
- ``reading``    text on a segment (a line's reading in a pass), or a reading of the node itself (a
                 translation, a regest, a folder's description; `representation.create`, #5599)
- ``page_text``  the page's own text (`Document.page_content`), not tied to segments
- ``mention``    a name: a `KnowledgeEntity` (or a merge of entities) found in the source
- ``statement``  a `KnowledgeClaim` (or an interpretation resting on a passage)
- ``entry``      a logical unit: a diary entry over part of a page
- ``table_row``  a row of a table on its lines
- ``attribute``  a field of the node: date columns, attributes, `metadata` fields
- ``node``       a child document (a page, a chapter, a cut, a folder of a cluster)
- ``rendition``  an image derived from the page (a cut, an enhancement, an edit chain)
- ``artifact``   an `Artifact` row on a document
- ``none``       nothing in the project (in-flow transforms, sources, files written outside)

``anchors_at``: the finest level the output attaches to: ``segment``, ``page``, ``document``,
``group`` (a folder or collection) or ``none``.
"""

from __future__ import annotations

from typing import NamedTuple

WRITES = frozenset(
    {
        "pass",
        "reading",
        "page_text",
        "mention",
        "statement",
        "entry",
        "table_row",
        "attribute",
        "node",
        "rendition",
        "artifact",
        "none",
    }
)
ANCHORS = frozenset({"segment", "page", "document", "group", "none"})


class OutputDeclaration(NamedTuple):
    writes: frozenset[str]
    anchors_at: str


def _d(anchors_at: str, *writes: str) -> OutputDeclaration:
    return OutputDeclaration(frozenset(writes), anchors_at)


_NONE = _d("none", "none")
# An Artifact row on the document and nothing else: the review's "document-level artifact only".
_ARTIFACT = _d("document", "artifact")
# The per-section extractors: entities + claims through `_write_kg_rows`, and the section artifact. Each
# name is a mention at every place the page text writes it, and a claim whose words are found rests on
# them; where the page text is tied to its lines both name the line and its reading (#5488, #4932).
_KG_AND_ARTIFACT = _d("segment", "mention", "statement", "artifact")
# Entities and claims tied to the document only (writers outside `_write_kg_rows`).
_KG_ON_DOCUMENT = _d("document", "mention", "statement", "artifact")
_RENDITION = _d("document", "rendition")
_CUTS = _d("document", "node", "rendition")

TOOL_OUTPUTS: dict[str, OutputDeclaration] = {
    # ── sources: choose what a run reads ──────────────────────────────────────
    # `files` splits a PDF that has no page children yet into pages (sources.py, #2430).
    "files": _d("document", "node"),
    "collection": _NONE,
    "selection": _NONE,
    "folder": _NONE,
    "search": _NONE,
    "annotations_source": _NONE,  # crops into the run's scratch folder
    "artifacts_source": _NONE,
    # ── reading and line finding: passes of segments ──────────────────────────
    "detect_regions": _d("segment", "pass", "reading", "artifact"),
    "align_transcript": _d("segment", "pass", "reading", "artifact"),
    "merge_geometry": _d("segment", "pass", "reading", "artifact"),
    # page text (update_page_content=True); a result with boxes also becomes a pass (#5222)
    "transcribe": _d("segment", "page_text", "pass", "reading", "artifact"),
    # run on a segment (#5604), its read is a reading on that segment
    "handwriting": _d("segment", "page_text", "reading", "artifact"),
    "transcribe_review": _d("page", "page_text", "artifact"),
    "audio_transcribe": _d("document", "page_text", "artifact"),
    "video_describe": _d("document", "page_text", "artifact"),
    "economy_htr": _NONE,  # hands its lines to the next step (records port)
    # ── structure: nodes ───────────────────────────────────────────────────────
    "book_structure": _d("document", "node"),
    "detect_structure": _d("document", "node"),
    "split_chapters": _d("document", "node"),
    "diary_entries": _d("page", "entry", "attribute"),
    "organize_same_documents": _d("group", "node"),
    "split_images": _CUTS,
    "split_pages": _CUTS,
    "segment_images": _CUTS,
    # ── document fields ────────────────────────────────────────────────────────
    "date_extract": _d("document", "attribute", "artifact"),
    # `metadata["geo_points"]`, the `geo` artifact, and place values on the claims
    "extract_geo": _d("document", "attribute", "statement", "artifact"),
    # ── knowledge graph rows tied to the document ─────────────────────────────
    # through `_write_kg_rows`: names, claims and quotations on their lines when tied (#5488, #4932, #5598)
    "extract_all": _d("segment", "mention", "statement", "artifact"),
    "people_extract": _KG_AND_ARTIFACT,
    "places_extract": _KG_AND_ARTIFACT,
    "organizations_extract": _KG_AND_ARTIFACT,
    "rivers_extract": _KG_AND_ARTIFACT,
    "events_extract": _KG_AND_ARTIFACT,
    "mines_extract": _KG_AND_ARTIFACT,
    "properties_extract": _KG_AND_ARTIFACT,
    "legal_references_extract": _KG_AND_ARTIFACT,
    "citation_usage_extract": _KG_ON_DOCUMENT,  # its own writer (`_write_citation_usage_rows`)
    "hermeneutics_extract": _KG_AND_ARTIFACT,
    # a quotation is a statement on the quoted words' span and, where the page text is tied to its lines,
    # on the line they start on; its speaker a mention on the name's span (#5598)
    "quotes_extract": _d("segment", "mention", "statement", "artifact"),
    "keywords_extract": _KG_AND_ARTIFACT,
    "dates_extract": _d("segment", "statement", "artifact"),  # dates are claims, no entity
    "book_index_extract": _KG_ON_DOCUMENT,
    "citations_extract": _d("document", "mention", "statement"),
    # a name is a mention at each place the page writes it (spaCy's spans, or a model's name found as
    # written), on its line when the page is tied (#5488)
    "extract_entities_only": _d("segment", "mention"),
    # these two write through `_write_kg_rows`: mentions and claims on their lines when tied (#5488, #4932)
    "extract_svo_only": _d("segment", "mention", "statement"),
    "kg_writer": _d("segment", "mention", "statement"),
    "merge_dedup_only": _d("document", "mention", "statement"),
    "kg_persist_finalize": _d("document", "statement"),  # support counts on claims
    "interpret": _d("document", "statement"),  # interpretations of a passage
    # page cleanup merges entities and saves the cleaned list on the page; folder cleanup on the folder
    **{
        f"{kind}_page_cleanup": _d("document", "mention", "artifact")
        for kind in ("people", "places", "organizations", "dates", "events", "keywords")
    },
    **{
        f"{kind}_folder_cleanup": _d("group", "mention", "artifact")
        for kind in ("people", "places", "organizations", "dates", "events", "keywords")
    },
    # the narrative is a description reading of the folder, never its text (#5599); artifacts beside
    "catalogue": _d("group", "reading", "artifact"),
    # ── text outputs that are readings (#5599): a reading of the node, derived from the run's artifact
    # (`LLMToolConfig.reading_kind`); not yet on the lines (#3325)
    "text_translate": _d("document", "reading", "artifact"),
    "text_translate_review": _d("document", "reading", "artifact"),
    "translate": _d("document", "reading", "artifact"),
    # the historical presets name their reading kind (translation, normalized_text, regest); an
    # analyze node that names none still writes only an 'analysis' artifact
    "analyze": _d("page", "reading", "artifact"),
    # descriptions: a caption or a description of the page is a `description` reading of it
    "caption": _d("segment", "reading", "artifact"),  # on a segment when run on one (#5604)
    "describe": _d("segment", "reading", "artifact"),
    # a summary is a `description` reading on what it summarises (`summarize` runs summarize_file)
    "summarize": _d("document", "reading", "artifact"),
    "summarize_file": _d("document", "reading", "artifact"),
    "summarize_folder": _d("group", "reading", "artifact"),
    "summarize_collection": _d("group", "reading", "artifact"),
    # the cleaned text is `normalized_text`; a rewrite is a `paraphrase` (a `translation` when it
    # names a target language)
    "clean_text": _d("document", "reading", "artifact"),
    "rewrite": _d("document", "reading", "artifact"),
    # Markdown / HTML / SVG are readings of those kinds; LaTeX and CSV write only the artifact
    "convert": _d("page", "reading", "artifact"),
    # ── attributes that cite their run (#5600, `LLMToolConfig.attribute_key`) ──
    # the kind is proposed as the node's prototype (`document.assign_prototype`), citing the run in
    # `metadata.attribute_sources`; a kind a person chose is kept
    "classify": _d("page", "attribute", "artifact"),
    # the scene type and its details are page attributes (`scene`, `scene_<field>`), citing the run
    "scene": _d("page", "attribute", "artifact"),
    # ── a document-level artifact only (known gaps, each naming its slice) ────
    "timeline": _ARTIFACT,
    "key_people": _ARTIFACT,
    "sentiment": _ARTIFACT,
    "keywords": _ARTIFACT,
    "tags": _ARTIFACT,
    "classify_text": _ARTIFACT,
    "classify_script": _ARTIFACT,
    "questions": _ARTIFACT,
    "extract": _ARTIFACT,
    "faces": _ARTIFACT,
    "objects": _ARTIFACT,
    "layout": _ARTIFACT,
    "diagram": _ARTIFACT,
    "style": _ARTIFACT,
    "quality": _ARTIFACT,
    "safety": _ARTIFACT,
    "colors": _ARTIFACT,
    "language_identification": _ARTIFACT,
    "compare": _ARTIFACT,
    "table_extract": _ARTIFACT,
    "extract_entities": _ARTIFACT,
    "import_artifacts": _ARTIFACT,
    "similarity": _d("group", "artifact"),
    # ── images: the output is an image ────────────────────────────────────────
    "rotate_images": _RENDITION,
    "prepare_images": _RENDITION,
    "enhance_images": _RENDITION,
    "denoise_images": _RENDITION,
    "fuzzy_clean_images": _RENDITION,
    "deskew_images": _RENDITION,
    "remove_background_images": _RENDITION,
    "auto_crop_border_images": _RENDITION,
    "adaptive_binarize_images": _RENDITION,
    "recombine_segments": _RENDITION,
    "zoom": _NONE,  # enlarged files into the run's scratch folder
    # ── in-flow transforms, logic, agents and outputs outside the project ─────
    "ocr_cleanup": _NONE,
    "text_reflow": _NONE,
    "consistency-check": _NONE,
    "aggregate": _NONE,
    "detect_ai_text": _NONE,
    "ner": _NONE,
    "model_comparison": _NONE,
    # A sub-workflow's and an agent's writes are those of the steps and audited actions they call.
    "sub_workflow": _NONE,
    "agent_coordinator": _NONE,
    "cli_agent": _NONE,
    "react_agent": _NONE,
    "supervisor_agent": _NONE,
    "swarm_agent": _NONE,
    "research_web_search": _NONE,
    "research_browser_navigate": _NONE,
    "research_document_fetch": _d("document", "node"),  # optionally files the page as a source
    "write_file": _NONE,
    "export_documents": _NONE,
    # Palette definitions with no implementation (registry_builtins): they cannot run.
    **{
        name: _NONE
        for name in (
            "enhance", "crop", "rotate", "segment", "custom_llm",
            "if", "switch", "loop", "filter", "merge",
            "to_pdf", "to_word", "to_excel", "to_json", "save_to_library", "export",
        )
    },
}


def declaration_for(tool_name: str) -> OutputDeclaration | None:
    """The tool's declaration, or None when it has none (the guard fails that)."""
    return TOOL_OUTPUTS.get(tool_name)


# ── Which steps run on a segment (#5604, `source.extract.run-on-any-level`) ─────
#
# A step declared at page or document level cannot be given a segment, unless it is a reader wired
# to take one: these read the segment's own picture (cut to it, `media/segment_pictures.py`) through
# `process_vision`, and what they read is written as a reading ON the segment (`llm_base`'s save,
# `outputs-attach-at-their-level`), never as the page's text. Any other step is refused with words
# before the run starts.

#: The sources that resolve a segment selection (`sources.files_tool`; `selection` calls it).
SEGMENT_SOURCES = frozenset({"files", "selection"})
#: The readers wired to a segment: each declares a reading or the page's text, and reads a picture.
SEGMENT_READERS = frozenset({"transcribe", "handwriting", "caption", "describe"})


def runs_on_segments(tool_name: str) -> bool:
    """Whether a step of this tool can be run on a segment selection."""
    return tool_name in SEGMENT_SOURCES or tool_name in SEGMENT_READERS
