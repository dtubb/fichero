"""
Workflow Tools

Individual tool implementations for workflow nodes.
Each tool is a simple async function that processes state.

Categories:
- vision: Image/document understanding (transcribe, describe, analyze)
- transform: Image manipulation (enhance, rotate, crop, segment)
- convert: Format conversion (to_word, to_pdf, to_json)
- llm: Text processing (summarize, translate, classify)
- utility: Helper operations (list_files, filter, merge)
"""

# Import tools to register them
from fichero.workflows.tools import transcribe

__all__ = [
    "transcribe",
]
