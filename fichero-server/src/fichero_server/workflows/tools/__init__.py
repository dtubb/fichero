"""
Workflow Tools

Individual tool implementations for workflow nodes.
Each tool is a simple async function that processes state.

Categories:
- source: Data sources (collection, folder, search)
- vision: Image understanding (transcribe, describe, classify, caption, analyze, tags,
           colors, faces, layout, compare, convert, extract, objects, scene, quality,
           safety, diagram, table_extract, handwriting, style, similarity)
- llm: Text processing (summarize, entities, timeline, key_people, catalogue,
        rewrite, sentiment, keywords, questions, classify_text)
- agent: AI agents (react_agent, supervisor, swarm)
- mcp: Tools from MCP servers
- research: Sandboxed research agent tools (web search, browser navigate, document fetch)
"""

# Import tools to register them
# Source tools
from fichero_server.workflows.tools import sources
from fichero_server.workflows.tools import annotations_source  # noqa: F401  (#914)

# Vision tools (use shared vision_base)
from fichero_server.workflows.tools import transcribe
from fichero_server.workflows.tools import transcribe_review  # noqa: F401  (registers the tool via @register_tool)
from fichero_server.workflows.tools import detect_regions  # noqa: F401  (bboxes-first pre-pass, 2026-08-11)
from fichero_server.workflows.tools import describe
from fichero_server.workflows.tools import classify
from fichero_server.workflows.tools import classify_script  # noqa: F401  (registers classify_script tool)
from fichero_server.workflows.tools import caption
from fichero_server.workflows.tools import analyze
from fichero_server.workflows.tools import tags
from fichero_server.workflows.tools import colors
from fichero_server.workflows.tools import faces
from fichero_server.workflows.tools import layout
from fichero_server.workflows.tools import compare
from fichero_server.workflows.tools import convert
from fichero_server.workflows.tools import extract
from fichero_server.workflows.tools import objects
from fichero_server.workflows.tools import scene
from fichero_server.workflows.tools import quality
from fichero_server.workflows.tools import safety
from fichero_server.workflows.tools import diagram
from fichero_server.workflows.tools import table_extract
from fichero_server.workflows.tools import handwriting
from fichero_server.workflows.tools import style
from fichero_server.workflows.tools import similarity
from fichero_server.workflows.tools import organize_same_documents  # noqa: F401  (#2284 slice 2)
from fichero_server.workflows.tools import rotate_images  # noqa: F401  (#1387)
from fichero_server.workflows.tools import prepare_images  # noqa: F401  (#1390)
from fichero_server.workflows.tools import enhance_images  # noqa: F401  (#1388)
from fichero_server.workflows.tools import fuzzy_clean_images  # noqa: F401  (#1389)
from fichero_server.workflows.tools import denoise_images  # noqa: F401  (#3606)
from fichero_server.workflows.tools import deskew_images  # noqa: F401  (#3611)
from fichero_server.workflows.tools import auto_crop_border_images  # noqa: F401  (#1385)
from fichero_server.workflows.tools import adaptive_binarize_images  # noqa: F401  (#3623)
from fichero_server.workflows.tools import remove_background_images  # noqa: F401  (#1393)
from fichero_server.workflows.tools import segment_images  # noqa: F401  (#1391)
from fichero_server.workflows.tools import recombine_segments  # noqa: F401  (#1392)
from fichero_server.workflows.tools import split_images  # noqa: F401  (#1394)

# LLM tools
from fichero_server.workflows.tools import summarize
from fichero_server.workflows.tools import entities
from fichero_server.workflows.tools import interpret  # noqa: F401  (hermeneutic layer first writer, 2026-08-12)
from fichero_server.workflows.tools import geo_extract  # noqa: F401  (#2266 registers extract_geo)
from fichero_server.workflows.tools import timeline
from fichero_server.workflows.tools import key_people
from fichero_server.workflows.tools import catalogue
from fichero_server.workflows.tools import ner
from fichero_server.workflows.tools import rewrite
from fichero_server.workflows.tools import sentiment
from fichero_server.workflows.tools import keywords
from fichero_server.workflows.tools import questions
from fichero_server.workflows.tools import classify_text
from fichero_server.workflows.tools import language_identification
from fichero_server.workflows.tools import detect_ai_text  # noqa: F401  (#753)
from fichero_server.workflows.tools import clean_text  # LLM text cleanup
from fichero_server.workflows.tools import translate  # noqa: F401  translation tool
from fichero_server.workflows.tools import text_translate  # noqa: F401  LLM translation (#926)
from fichero_server.workflows.tools import text_translate_review  # noqa: F401  translation double-check (#926)
from fichero_server.workflows.tools import extractors  # per-section catalogue extractors
from fichero_server.workflows.tools import extract_all  # combined single-call extractor
from fichero_server.workflows.tools import kg_writer
from fichero_server.workflows.tools import book_structure
from fichero_server.workflows.tools import detect_structure
from fichero_server.workflows.tools import citations_extract
from fichero_server.workflows.tools import date_extract  # historical dates -> JDN (#3322)
from fichero_server.workflows.tools import cleanup  # per-section page/folder canonical cleanup
from fichero_server.workflows.tools import import_artifacts  # noqa: F401  (#1757 step 1)
from fichero_server.workflows.tools import extract_entities_only  # noqa: F401  (#1757 step 2)
from fichero_server.workflows.tools import extract_svo_only  # noqa: F401  (#1757 step 3)
from fichero_server.workflows.tools import merge_dedup_only  # noqa: F401  (#1757 step 4)
from fichero_server.workflows.tools import kg_persist_finalize  # noqa: F401  (#1757 step 5)

# Audio tools (use shared audio_base)
from fichero_server.workflows.tools import audio_transcribe

# Video tools (use shared video_base)
from fichero_server.workflows.tools import video_describe

# Agent tools
from fichero_server.workflows.tools import agent
from fichero_server.workflows.tools import cli_agent
from fichero_server.workflows.tools import multi_agent
from fichero_server.workflows.tools import mcp

# Research tools
from fichero_server.workflows.tools import research

# The model_comparison tool lives OUTSIDE this package, in
# fichero/workflows/model_comparison.py. It is imported here anyway because
# this file — not any other import — is what owns tool registration (#3951).
#
# Before #3950 it registered only as a side effect of
# api/routes/model_comparison.py importing the module at engine startup. That
# is precisely how zoom and consistency_check vanished: a tool whose
# registration depends on some unrelated module happening to be imported is a
# tool that silently disappears the moment that import moves. Deferring the
# route imports made it real — the registry dropped to 117 tools with no error.
#
# If this import is ever removed, model_comparison stops existing.
from fichero_server.workflows import model_comparison  # noqa: F401  (#3950/#3951)

# Transform tools (fan-in, reshape, cleanup)
from fichero_server.workflows.tools import aggregate
from fichero_server.workflows.tools import sub_workflow  # noqa: F401  (#2201)
from fichero_server.workflows.tools import ocr_cleanup  # noqa: F401  (#925)
from fichero_server.workflows.tools import text_reflow  # noqa: F401  (#1260)
from fichero_server.workflows.tools import book_index  # noqa: F401  (#1278)
from fichero_server.workflows.tools import split_chapters  # noqa: F401  (#1315)
from fichero_server.workflows.tools import consistency_check  # noqa: F401  (#3910)

# Transform tools
from fichero_server.workflows.tools import zoom  # noqa: F401  (#3903)

# Output tools
from fichero_server.workflows.tools import write_file
from fichero_server.workflows.tools import export_documents  # noqa: F401

__all__ = [
    # Source
    "sources",
    # Vision
    "transcribe",
    "detect_regions",
    "describe",
    "classify",
    "classify_script",
    "caption",
    "analyze",
    "tags",
    "colors",
    "faces",
    "layout",
    "compare",
    "convert",
    "extract",
    "objects",
    "scene",
    "quality",
    "safety",
    "diagram",
    "table_extract",
    "handwriting",
    "style",
    "similarity",
    "organize_same_documents",
    "rotate_images",
    "prepare_images",
    "enhance_images",
    "fuzzy_clean_images",
    "remove_background_images",
    "segment_images",
    "recombine_segments",
    "split_images",
    # LLM
    "summarize",
    "entities",
    "timeline",
    "key_people",
    "catalogue",
    "ner",
    "rewrite",
    "sentiment",
    "keywords",
    "questions",
    "classify_text",
    "language_identification",
    "detect_ai_text",
    "clean_text",
    "translate",
    "text_translate",
    "text_translate_review",
    "extractors",
    "extract_all",
    "kg_writer",
    "book_structure",
    "detect_structure",
    "citations_extract",
    "date_extract",
    "cleanup",
    "import_artifacts",
    "extract_entities_only",
    "extract_svo_only",
    "merge_dedup_only",
    "kg_persist_finalize",
    # Audio
    "audio_transcribe",
    # Video
    "video_describe",
    # Agent
    "agent",
    "cli_agent",
    "multi_agent",
    "mcp",
    # Research
    "research",
    # Transform
    "aggregate",
    "sub_workflow",
    "ocr_cleanup",
    "text_reflow",
    "book_index",
    "split_chapters",
    # Output
    "write_file",
    "export_documents",
]
