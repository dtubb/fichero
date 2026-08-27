#!/usr/bin/env python3
"""Generate the landing-page release snippets from RELEASE_NOTES.md.

Writes two files under docs/ (both excluded from the mkdocs page build;
they are pulled into index.md via pymdownx.snippets):

  docs/_latest.md    — one line naming the newest release
  docs/_releases.md  — first third of the newest release as a teaser; the
                       rest of it and all older releases inside a native
                       <details> "Show more releases" block

Run from the repo root. Deterministic; re-run any time RELEASE_NOTES.md
changes (deploy-site.sh runs it before every build).
"""

import math
import re
from pathlib import Path
SRC = Path("RELEASE_NOTES.md")
OUT_DIR = Path("docs")

text = SRC.read_text(encoding="utf-8")

# Split into (version, body) pairs on "## <version>" headings.
parts = re.split(r"^## (.+)$", text, flags=re.M)[1:]
releases = [(parts[i].strip(), parts[i + 1].strip()) for i in range(0, len(parts) - 1, 2)]
if not releases:
    raise SystemExit("gen_site_releases: no '## <version>' headings found in RELEASE_NOTES.md")


def render(version: str, body: str) -> str:
    # Demote any headings inside the body so the page outline stays sane.
    body = re.sub(r"^(#{2,5}) ", r"#\1 ", body, flags=re.M)
    return f"### {version}\n\n{body}\n"


# Show the newest release only, and only the first third of it (split on
# blank-line blocks so bullets aren't cut mid-item); the remainder and all
# older releases live inside the expander.
latest_version, latest_body = releases[0]
blocks = re.split(r"\n\s*\n", latest_body)
cut = max(1, math.ceil(len(blocks) / 3))
teaser = "\n\n".join(blocks[:cut])
remainder = "\n\n".join(blocks[cut:])

releases_md = render(latest_version, teaser)
hidden = ""
if remainder:
    hidden += remainder + "\n\n"
hidden += "\n".join(render(v, b) for v, b in releases[1:])
if hidden.strip():
    releases_md += (
        "\n<details markdown>\n<summary>Show more releases</summary>\n\n"
        + hidden
        + "\n</details>\n"
    )

(OUT_DIR / "_releases.md").write_text(releases_md, encoding="utf-8")
(OUT_DIR / "_latest.md").write_text(
    f"Latest release: **{releases[0][0]}**\n", encoding="utf-8"
)
print(f"gen_site_releases: {len(releases)} releases, teaser {cut}/{len(blocks)} blocks of latest {latest_version}")
