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
from fichero.prompts import load_prompt

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
from typing import Any

import yaml

_PROMPTS_DIR = (
    Path(__file__).resolve().parent / "resources" / "prompts"
)


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
