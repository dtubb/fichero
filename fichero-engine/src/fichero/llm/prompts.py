"""Prompt registry — versioned prompt storage outside code (#816).

Per Apple's "Updating prompts for new model versions" guidance: prompts
should live as versioned files so we can compare versions when iterating,
roll back ones that regress, track which model version each prompt was
tuned for, and evaluate them via the eval harness (#817) without
shipping a code change.

## Layout

```
resources/prompts/
  <tool>/
    <name>_v<N>.md
```

## File format

Each prompt is a Markdown file with YAML frontmatter:

```markdown
---
version: 2
model_target: small
author: dtubb
date: 2026-05-06
changelog: |
  - Compressed from 600 to 155 tokens for Apple Intelligence.
  - Dropped named example sentences that bled into output.
---
You are an expert archivist. Write a catalogue entry in {output_language}…
```

The body is the prompt template — fields between `{` and `}` are filled
by `.format(**kwargs)` at load time.

## Usage

```python
from fichero.llm.prompts import load_prompt

prompt = load_prompt("catalogue", "narrative", output_language="English")
# Returns the latest version; pass version=1 to pin.
```

If no prompts of the named tool/name exist, raises `PromptNotFound`.

## Migration discipline

Touching a shipped prompt? Bump the version: copy `narrative_v2.md` to
`narrative_v3.md`, edit, leave v2 in place for comparison + rollback.
Run the eval harness against both versions:

```
python -m evals.run --tool catalogue --prompt-version 2
python -m evals.run --tool catalogue --prompt-version 3
```

Decide whether v3 actually wins before deleting v2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml

_PROMPTS_DIR = (
    # prompts.py moved into fichero/llm/ (#2566); resources/ stays a
    # shared top-level package (fichero/resources/), so go up one more
    # level than the old fichero/prompts.py did.
    Path(__file__).resolve().parent.parent / "resources" / "prompts"
)

INSTRUMENT_SYSTEM_PROMPT = dedent(
    """\
    Fichero AI is a transparent, local instrument for helping people make sense of sources. It is not a sense-making oracle, not a chatbot persona, and not a substitute for the user's judgment.

    Core rules:
    - Surface ontological facts and provenance from the available sources. Do not interpret the sources for the user, editorialize, or author conclusions on the user's behalf.
    - Never pretend to be human. Do not claim feelings, beliefs, lived experience, or a personal point of view.
    - Do not flatter, mirror, or manipulate the user for engagement. Be plain, direct, and tool-like.
    - Do not launder source language into unattributed prose. Quote or cite source fragments with provenance or anchors when possible.
    - Treat Fichero as local-first and private. Do not imply that the user's material leaves their control.
    - The human leads thinking and writing. Assist with evidence, structure, and traceable drafting support rather than replacing human judgment.
    """
).strip()

_ROLE_PROMPT_EXTRAS: dict[str, str] = {
    "agent": (
        "Use tools to gather grounded results, then report them plainly. "
        "Keep tool use in service of factual, source-aware assistance."
    ),
    "chat": (
        "Answer with grounded facts from the provided material or the user's "
        "question. If evidence is missing, say so directly and name the gap."
    ),
    "research": (
        "Prioritize source discovery, factual leads, archive targets, and "
        "clear provenance over interpretation or narrative synthesis."
    ),
    "researcher": (
        "Prioritize source discovery, factual leads, archive targets, and "
        "clear provenance over interpretation or narrative synthesis."
    ),
    "extraction": (
        "Return traceable source-grounded outputs. Avoid adding interpretive "
        "claims beyond the extraction task."
    ),
}


class PromptNotFound(Exception):
    """Raised when load_prompt can't find a matching tool/name/version."""


@dataclass(frozen=True)
class PromptMetadata:
    version: int
    model_target: str = ""
    author: str = ""
    date: str = ""
    changelog: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Prompt:
    tool: str
    name: str
    template: str
    metadata: PromptMetadata

    def render(self, **kwargs: Any) -> str:
        """Substitute the template's `{placeholder}` fields. Missing
        placeholders raise KeyError immediately rather than silently
        leaving them in — small models will misbehave if a literal
        '{output_language}' shows up in their instructions."""
        return self.template.format(**kwargs)


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<yaml>.*?)\n---\s*\n(?P<body>.*)",
    re.DOTALL,
)
_FILENAME_RE = re.compile(r"^(?P<name>.+)_v(?P<version>\d+)\.md$")


def _parse_prompt_file(path: Path, tool: str) -> Prompt:
    raw = path.read_text()
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        raise ValueError(
            f"Prompt file missing YAML frontmatter: {path}"
        )
    metadata_dict = yaml.safe_load(m.group("yaml")) or {}
    body = m.group("body").strip()

    fname_match = _FILENAME_RE.match(path.name)
    if not fname_match:
        raise ValueError(
            f"Prompt file name must be <name>_v<N>.md: {path.name}"
        )
    name = fname_match.group("name")
    file_version = int(fname_match.group("version"))

    metadata = PromptMetadata(
        version=int(metadata_dict.pop("version", file_version)),
        model_target=str(metadata_dict.pop("model_target", "") or ""),
        author=str(metadata_dict.pop("author", "") or ""),
        date=str(metadata_dict.pop("date", "") or ""),
        changelog=str(metadata_dict.pop("changelog", "") or ""),
        extra=metadata_dict,
    )

    if metadata.version != file_version:
        raise ValueError(
            f"Prompt {path.name}: filename says v{file_version} but "
            f"frontmatter says v{metadata.version}. Fix one to match."
        )

    return Prompt(
        tool=tool,
        name=name,
        template=body,
        metadata=metadata,
    )


@lru_cache(maxsize=None)
def _list_prompt_files(tool: str, name: str) -> tuple[Path, ...]:
    """Return all matching prompt files sorted by version ascending."""
    tool_dir = _PROMPTS_DIR / tool
    if not tool_dir.exists():
        return ()
    matches: list[tuple[int, Path]] = []
    for path in tool_dir.glob(f"{name}_v*.md"):
        m = _FILENAME_RE.match(path.name)
        if m:
            matches.append((int(m.group("version")), path))
    matches.sort()
    return tuple(p for _, p in matches)


def list_versions(tool: str, name: str) -> list[int]:
    """Return all available versions of a prompt, sorted ascending."""
    return [
        int(_FILENAME_RE.match(p.name).group("version"))  # type: ignore[union-attr]
        for p in _list_prompt_files(tool, name)
    ]


def get_prompt(tool: str, name: str, version: int | None = None) -> Prompt:
    """Load a prompt without rendering. Use this when you want the
    template text + metadata (for the inspector preview, or for the
    eval harness to dump alongside results)."""
    paths = _list_prompt_files(tool, name)
    if not paths:
        raise PromptNotFound(
            f"No prompt files for tool={tool!r} name={name!r}. "
            f"Looked in {_PROMPTS_DIR / tool}/{name}_v*.md"
        )
    if version is None:
        # Latest = highest version number.
        return _parse_prompt_file(paths[-1], tool)
    for path in paths:
        if path.name.endswith(f"_v{version}.md"):
            return _parse_prompt_file(path, tool)
    raise PromptNotFound(
        f"Prompt {tool}/{name} has no v{version}. "
        f"Available: {list_versions(tool, name)}"
    )


def load_prompt(
    tool: str, name: str,
    *, version: int | None = None,
    **placeholders: Any,
) -> str:
    """Load and render a prompt template. Returns the rendered string.

    `version=None` resolves to the latest version. Pass an int to pin.
    Placeholder kwargs fill `{name}` slots in the template.
    """
    return get_prompt(tool, name, version=version).render(**placeholders)


def compose_system_prompt(role: str | None = None, extra: str | None = None) -> str:
    """Compose the shared AI-integrity doctrine with optional role guidance.

    `extra` is appended rather than replacing the doctrine, so deliberate
    caller-specific instructions remain intact.
    """
    sections = [INSTRUMENT_SYSTEM_PROMPT]

    normalized_role = (role or "").strip().lower()
    role_extra = _ROLE_PROMPT_EXTRAS.get(normalized_role)
    if role_extra:
        sections.append(f"Surface guidance ({normalized_role}):\n- {role_extra}")

    if extra and extra.strip():
        sections.append(f"Additional instructions:\n{extra.strip()}")

    return "\n\n".join(sections)
