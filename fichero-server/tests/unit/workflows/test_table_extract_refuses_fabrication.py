"""Extract Table must be able to say "there is no table here".

The failure (2026-09-04, local-model sweep on Qwen2.5-VL-3B): Extract Table was
run on a manuscript page with no table on it, and returned a table — the
integers 0,1,2 … 30. It had read the **centimetre ruler** lying in the scan
margin, which is present in a large share of archival photography.

The tool's prompt only ever COMMANDED extraction. A model handed a page with no
table had no way to answer "none", so it answered with the closest thing to a
table in the frame. Nothing downstream checked, so the run reported success and
an archive gained thirty-one rows that nobody wrote.

This is a worse relative of the silent no-ops fixed the same week. Those
returned NOTHING while claiming success; this returns INVENTED DATA while
claiming success, into a corpus whose entire value is that its contents are
attested.

Two halves are pinned here:

* the rules that give the model an escape hatch ride with EVERY prompt, custom
  ones included — 'Accounts → Spreadsheet (CSV)' ships its own and is the
  preset most likely to meet a page of prose;
* the validator refuses the save, with a reason, for an empty answer, the
  no-table sentinel, and the ruler signature — and keeps real tables.

No model is called; the validator is a pure function over the reply text.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.tools.table_extract import (
    NO_TABLE_SENTINEL,
    build_table_prompt,
    validate_extracted_table,
    with_no_table_rules,
)

REAL_TABLE = '"Date","Entries","Amount"\n"Jan 1","12","3.40"\n"Jan 2","9","2.10"'

# The actual shape returned for the ruler, quoted as the CSV prompt demands.
RULER = "\n".join(f'"{n}"' for n in range(31))


# --- the escape hatch reaches every prompt ---------------------------------


def test_builtin_prompts_offer_the_no_table_answer() -> None:
    for style in ("csv", "json_rows", "json_columns", "markdown"):
        prompt = build_table_prompt({"output_style": style})
        assert NO_TABLE_SENTINEL in prompt, f"{style} prompt has no escape hatch"


def test_a_custom_prompt_gets_the_rules_too() -> None:
    """The accounts preset ships its own prompt; it must not be the exception."""
    custom = "Extract the account entries on this page into CSV."
    assert NO_TABLE_SENTINEL in with_no_table_rules(custom)


def test_appending_the_rules_is_idempotent() -> None:
    """The tool body appends to whatever prompt it ends up using."""
    once = with_no_table_rules("Extract the accounts.")
    assert with_no_table_rules(once) == once
    built = build_table_prompt({"output_style": "csv"})
    assert with_no_table_rules(built) == built


def test_the_rules_name_the_furniture_that_caused_this() -> None:
    prompt = build_table_prompt({"output_style": "csv"}).lower()
    assert "ruler" in prompt and "scale bar" in prompt


# --- the validator refuses what the page does not have ---------------------


def test_a_real_table_is_kept() -> None:
    assert validate_extracted_table(REAL_TABLE, "csv") == REAL_TABLE


def test_a_fenced_table_is_unwrapped_and_kept() -> None:
    fenced = f"```csv\n{REAL_TABLE}\n```"
    assert validate_extracted_table(fenced, "csv") == REAL_TABLE


@pytest.mark.parametrize("reply", [NO_TABLE_SENTINEL, "no table", "  No Table \n"])
def test_the_sentinel_refuses_the_save_with_a_reason(reply: str) -> None:
    with pytest.raises(ValueError, match="No table on this page"):
        validate_extracted_table(reply, "csv")


def test_an_empty_reply_refuses_the_save() -> None:
    with pytest.raises(ValueError, match="no output"):
        validate_extracted_table("   \n ", "csv")


def test_the_scan_ruler_is_refused_as_fabrication() -> None:
    """The exact output that prompted this fix."""
    with pytest.raises(ValueError, match="measuring ruler"):
        validate_extracted_table(RULER, "csv")


def test_a_genuine_one_column_tally_is_not_refused() -> None:
    """Marshall's dredge counts are one column and are NOT consecutive.

    The ruler check must not become a rule against single-column tables, which
    are ordinary in a ledger.
    """
    tally = "\n".join(f'"{n}"' for n in (12, 9, 14, 9, 27, 3, 18))
    assert validate_extracted_table(tally, "csv") == tally


def test_a_short_numbered_column_is_not_refused() -> None:
    """Three consecutive numbers are not a ruler; the signature needs length."""
    short = '"1"\n"2"\n"3"'
    assert validate_extracted_table(short, "csv") == short


def test_a_two_column_table_of_numbers_is_not_refused() -> None:
    """A ruler has one column. Numeric data with a second column is data."""
    paired = "\n".join(f'"{n}","{n * 3}"' for n in range(20))
    assert validate_extracted_table(paired, "csv") == paired
