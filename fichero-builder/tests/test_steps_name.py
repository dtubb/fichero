"""`builder steps` must reach the steps module: main() once assigned a local `steps` in its milestone branch, which made the
name local to the whole function (UnboundLocalError on `steps.run`)."""
from fichero_builder import __main__ as cli
from fichero_builder import steps


def test_the_steps_verb_reaches_the_steps_module(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(steps, "run", lambda spec, gh, dry_run: seen.append(spec))
    assert cli.main(["steps", "--spec", "S.md", "--state", str(tmp_path)]) == 0
    assert seen == ["S.md"]
