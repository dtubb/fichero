"""Every pytest the gate runs uses pytest-timeout's `thread` method (#6007, api signal hang).

WHY: `pytest.ini` keeps `timeout_method = signal` for a person's run, but the api part hung twice at ~41% with `signal` (a one-shot
SIGALRM that cannot run while another thread holds the GIL, or whose failure a teardown swallows) and ran clean with `thread`. A new
pytest line in scripts/gate that forgets the flag would bring the hang back."""
from __future__ import annotations

import re
from pathlib import Path

GATE = Path(__file__).resolve().parents[4] / "scripts" / "gate"


def test_every_pytest_the_gate_runs_names_the_thread_timeout_method():
    # a command line, with its backslash continuations joined
    text = GATE.read_text().replace("\\\n", " ")
    runs = [ln for ln in text.splitlines() if re.search(r"-m pytest\b", ln) and not ln.lstrip().startswith("#")]
    assert len(runs) >= 4, "the gate's pytest lines moved: update this test"
    missing = [ln.strip()[:90] for ln in runs if "--timeout-method=thread" not in ln]
    assert not missing, f"a gate pytest run without --timeout-method=thread: {missing}"


def test_the_other_gate_scripts_use_it_too_and_none_goes_back_to_signal():
    """verify_python.sh said "signal, NOT thread" (#5071) until #6007; the whole-suite gates now say thread, each citing #6007."""
    scripts = GATE.parent
    for name in ("verify_python.sh", "verify_all.sh", "build-and-validate.sh"):
        text = (scripts / name).read_text()
        assert "--timeout-method=thread" in text, f"{name} runs pytest without the thread timeout method"
        assert "--timeout-method=signal" not in text, f"{name} went back to the signal timeout method (#6007)"
    assert "#6007" in (scripts / "verify_python.sh").read_text(), "the flip must cite #6007 against #5071"
