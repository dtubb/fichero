"""#6124: Share Log exports the subsystem `LogExport.subsystem`; a Logger under another subsystem is missing from it."""
from __future__ import annotations

import re
from pathlib import Path

from _scan_files import scan_rglob

APP = Path(__file__).resolve().parents[4] / "fichero" / "fichero"
SUBSYSTEM = "app.fichero.fichero"


def test_every_app_logger_uses_the_subsystem_share_log_exports():
    export = (APP / "Services" / "LogExport.swift").read_text()
    assert f'static let subsystem = "{SUBSYSTEM}"' in export
    stray = [
        f"{path.relative_to(APP)}: {m.group(0)}"
        for path in scan_rglob(APP, "*.swift")
        for m in re.finditer(r'Logger\(subsystem: [^,)]+', path.read_text())
        if m.group(0) != f'Logger(subsystem: "{SUBSYSTEM}"'
    ]
    assert not stray, "loggers outside the Share Log subsystem:\n" + "\n".join(stray)
