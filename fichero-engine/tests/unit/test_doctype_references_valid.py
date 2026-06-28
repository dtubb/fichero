"""#2507 guard: every `DocType.<member>` reference must be a real enum member.

The `DocType.web_capture` typo sat in two write paths for a long time —
`DocType` has no such member, so each Document(...) raised AttributeError that
a silent/blanket except swallowed, making "save as source" a no-op. A bad enum
attribute is a hard error that should never reach a catch-all, so pin it: scan
the shipped source for DocType attribute access and validate against the enum.
"""

from __future__ import annotations

import re
from pathlib import Path

from fichero.models import DocType

_SRC = Path(__file__).resolve().parents[2] / "src" / "fichero"
# `DocType.<name>` where <name> is a plain identifier (skip method-y calls).
_REF = re.compile(r"\bDocType\.([A-Za-z_][A-Za-z0-9_]*)")
# Enum dunders / helpers that legitimately appear as DocType.<x>.
_ALLOWED_NON_MEMBERS = {"value", "name", "values", "__members__"}


def test_all_doctype_attribute_refs_are_valid_members():
    valid = {m.name for m in DocType} | _ALLOWED_NON_MEMBERS
    offenders: list[str] = []

    for path in _SRC.rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for member in _REF.findall(line):
                if member not in valid:
                    rel = path.relative_to(_SRC.parents[1])
                    offenders.append(f"{rel}:{i} DocType.{member}")

    assert not offenders, (
        "Invalid DocType members referenced (real members: "
        f"{sorted(m.name for m in DocType)}):\n  " + "\n  ".join(offenders)
    )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
