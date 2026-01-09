"""
Workflow Tools

Individual tool implementations for workflow nodes.
Each tool is a simple async function that processes state.

Categories:
- agent: AI agents with tool-calling abilities (react_agent)
- mcp: Tools from MCP (Model Context Protocol) servers
- vision: Image/document understanding (transcribe, describe, analyze)
- transform: Image manipulation (enhance, rotate, crop, segment)
- convert: Format conversion (to_word, to_pdf, to_json)
- llm: Text processing (summarize, translate, classify)
- utility: Helper operations (list_files, filter, merge)
"""

# Import tools to register them
from fichero.workflows.tools import agent
from fichero.workflows.tools import transcribe
from fichero.workflows.tools import mcp

__all__ = [
    "agent",
    "transcribe",
    "mcp",
]
