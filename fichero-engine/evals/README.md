# Prompt evaluation harness (#817)

Tests fichero's LLM prompts against fixed scenarios with measurable criteria.

Per Apple's "Evaluating prompts" guide: every prompt change risks regression.
Manual eyeball-comparison of one folder is unreliable — this directory exists
so any prompt change can be re-run against a stable scenario library and
graded against rule-based criteria.

## Layout

```
evals/
  scenarios/    # input transcripts, one .txt per fixed test case
  criteria/    # YAML rule lists per (tool, scenario) pair
  results/     # markdown reports written by run.py, dated + model-tagged
  run.py       # CLI runner
```

## Scenarios

A scenario is a piece of source text the tool would normally see at run time.
Each scenario lives as a single `.txt` file under `scenarios/`. Naming
convention: `<archive_or_genre>_<approx_date>_<short_title>.txt`.

Currently shipped:
- `book_preface_tubb_2020.txt` — English chapter preface with Spanish loanwords
- `court_file_chocó_1930_bonilla.txt` — Spanish court case (Tubb's archive)
- `bill_of_sale_popayán_1699_mateo.txt` — Spanish notarial deed
- `adversarial_empty.txt` — empty input, model should refuse cleanly
- `adversarial_garbage.txt` — random bytes, model should refuse cleanly

Add more by dropping a `.txt` and a matching criteria file.

## Criteria

A criteria file lists checks for one (tool, scenario) pair as YAML:

```yaml
tool: catalogue
scenario: book_preface_tubb_2020
checks:
  - kind: not_contains
    value: "vibrant tapestry"
    rationale: "Purple-prose phrase the small-model default leaks. Must be absent."
  - kind: not_contains
    value: "Antonio Asprilla"
    rationale: "Prompt-bleed sentinel — example name from prior prompt revisions."
  - kind: word_count_between
    min: 200
    max: 450
    rationale: "Long-source narrative range from the format spec (#824)."
  - kind: contains
    value: "Chocó"
    rationale: "Source mentions Chocó repeatedly; narrative should preserve it."
```

### Check kinds (extend `run.py:_apply_check` to add more)

- `contains` / `not_contains`  — substring match
- `regex_match` / `regex_no_match` — regex match
- `word_count_between` — `min` / `max` integers
- `starts_with` — first non-whitespace chars
- `ratio_to_gold` — fuzzy similarity (`difflib.SequenceMatcher`) ≥ `min`

## Runner

```bash
PYTHONPATH=fichero-engine/src .venv/bin/python -m evals.run \
    --tool catalogue \
    --model openrouter/qwen/qwen3-72b-instruct \
    --scenarios book_preface_tubb_2020,court_file_chocó_1930_bonilla
```

Defaults: all scenarios for the named tool, model from current settings.
Writes a markdown report to `results/<timestamp>_<model>_<tool>.md` with
per-scenario pass/fail and the failing checks' rationales.

## Workflow integration

Future: pre-commit hook runs the harness on any prompt-touching diff.
Today: run manually before merging prompt changes.
