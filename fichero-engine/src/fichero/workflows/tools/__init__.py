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
from fichero.workflows.tools import sources

# Vision tools (use shared vision_base)
from fichero.workflows.tools import transcribe
from fichero.workflows.tools import describe
from fichero.workflows.tools import classify
from fichero.workflows.tools import caption
from fichero.workflows.tools import analyze
from fichero.workflows.tools import tags
from fichero.workflows.tools import colors
from fichero.workflows.tools import faces
from fichero.workflows.tools import layout
from fichero.workflows.tools import compare
from fichero.workflows.tools import convert
from fichero.workflows.tools import extract
from fichero.workflows.tools import objects
from fichero.workflows.tools import scene
from fichero.workflows.tools import quality
from fichero.workflows.tools import safety
from fichero.workflows.tools import diagram
from fichero.workflows.tools import table_extract
from fichero.workflows.tools import handwriting
from fichero.workflows.tools import style
from fichero.workflows.tools import similarity

# LLM tools
from fichero.workflows.tools import summarize
from fichero.workflows.tools import entities
from fichero.workflows.tools import timeline
from fichero.workflows.tools import key_people
from fichero.workflows.tools import catalogue
from fichero.workflows.tools import rewrite
from fichero.workflows.tools import sentiment
from fichero.workflows.tools import keywords
from fichero.workflows.tools import questions
from fichero.workflows.tools import classify_text
from fichero.workflows.tools import extractors  # per-section catalogue extractors
from fichero.workflows.tools import extract_all  # combined single-call extractor
from fichero.workflows.tools import cleanup  # per-section page/folder canonical cleanup

# Audio tools (use shared audio_base)
from fichero.workflows.tools import audio_transcribe

# Video tools (use shared video_base)
from fichero.workflows.tools import video_describe

# Agent tools
from fichero.workflows.tools import agent
from fichero.workflows.tools import multi_agent
from fichero.workflows.tools import mcp

# Research tools
from fichero.workflows.tools import research

# Transform tools (fan-in, reshape)
from fichero.workflows.tools import aggregate

# Output tools
from fichero.workflows.tools import write_file

__all__ = [
    # Source
    "sources",
    # Vision
    "transcribe",
    "describe",
    "classify",
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
    # LLM
    "summarize",
    "entities",
    "timeline",
    "key_people",
    "catalogue",
    "rewrite",
    "sentiment",
    "keywords",
    "questions",
    "classify_text",
    "extractors",
    "extract_all",
    "cleanup",
    # Audio
    "audio_transcribe",
    # Video
    "video_describe",
    # Agent
    "agent",
    "multi_agent",
    "mcp",
    # Research
    "research",
    # Transform
    "aggregate",
    # Output
    "write_file",
]
