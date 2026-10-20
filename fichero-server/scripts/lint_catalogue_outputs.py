"""Lint a directory of recorded catalogue outputs (*.txt) against the 200-word cap (#5968).

M4 live comparison: write each prompt's output for a folder to <dir>/<kind>-<name>.txt (kind: long, folder or short),
run this, and drop the files that pass into tests/unit/llm/golden_catalogue/. Exit 1 on any error; warnings print only.
"""
import sys
from pathlib import Path

from fichero_server.llm.catalogue_lint import check

failed = False
for path in sorted(Path(sys.argv[1]).glob("*.txt")):
    errors, warnings = check(path.read_text(), long_item=not path.stem.startswith("short-"))
    print(path.name, len(path.read_text().split()), "words", *("ERROR " + e for e in errors), *("warn " + w for w in warnings), sep="\n  " if errors or warnings else " ")
    failed |= bool(errors)
sys.exit(1 if failed else 0)
