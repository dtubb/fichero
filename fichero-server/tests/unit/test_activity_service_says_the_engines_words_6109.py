"""Every ActivityService call that gets an undocumented answer says the engine's words (#6109,
`activity.service.refusals-in-the-engines-words`): no `.undocumented` branch drops its payload."""
from __future__ import annotations

import re
from pathlib import Path

SERVICES = sorted((Path(__file__).resolve().parents[3] / "fichero/fichero/Services").glob("ActivityService*.swift"))


def test_no_undocumented_branch_drops_the_engines_payload():
    dropped = []
    for path in SERVICES:
        source = path.read_text(encoding="utf-8")
        dropped += [f"{path.name}:{source[:m.start()].count(chr(10)) + 1}"
                    for m in re.finditer(r"case \.undocumented\(let \w+, _\)", source)]
    assert not dropped, f"{dropped}: .undocumented binds _ for the payload; use ActivityServiceError.failure"


def test_the_scan_sees_the_services_undocumented_branches():
    source = "".join(p.read_text(encoding="utf-8") for p in SERVICES)
    assert len(SERVICES) >= 5 and source.count("case .undocumented(") >= 10 and "ActivityServiceError.failure(" in source  # not a scan of nothing
