"""Account pages are not diary entries, even when their line items carry dates (#5559).

Spec: docs/contributor_manual/specs/source/historical-text-normalization.md (histnorm.dates.*).

WHY: the final #5557 rerun on a fresh clone of the Marshall Diaries dated the account pages at
the back of the books from their line items: the 1943-45 expense and bank pages (IMG_081-087,
"Nov. 1 Lunch and taxi at Panama $1.80" -> 1944-11-01), the 1940 "Bank balance Irving Trust
Co. Jan.1, 1940" page, and the 1941 "Insurance Due:" page, whose "October 28 - Sun Life
Assurance" was read as a Sunday and flagged. These are the dates of items in an account, not
of entries. The non-entry markers now name "Expense Account", "Bank balance" and "Insurance
Due", a column of dated line items with amounts and no weekday heading is an account page,
and a weekday abbreviation that starts a name ("Sun Life") is not a weekday.

Every string is the real one from the review dump (the page's first lines).
"""

from __future__ import annotations

import pytest

from fichero_server.histdate import find_page_date, gregorian_to_jdn, years_from_name

V1943_45 = "NCM_Diary_19431017-19450922"

ACCOUNT_PAGES = [
    ("the 1940 bank balance (IMG_068_part_1)",
     "Bank balance Irving Trust Co. Jan.1, 1940\nCheck No. 802 out\n$19307.11\n1500.00\n$17807.11\n"
     "Check in mail not yet credited\n110.50\nActual balance:\n$17917.61\nCash on hand\n265.14\n"
     "Balance Jan. 1, 1940\n$18182.75", [1940], "BANK BALANCE"),
    ("the 1941 insurance list (IMG_064_part_2)",
     "Insurance Due:\nOctober 28 - Sun Life Assurance Co. of Canada, 1180 Raymond Blvd.,\nNewark\n"
     "$236.50 Policy No. 902271.\nNovember 14 - The Equitable Life Assurance Society of the\n"
     "$1000.** Policy #9285397. \\ 393 Seventh Avuly 17 - The Mutual Life", [1941], "INSURANCE DUE"),
    ("the 1943-45 expense account (IMG_083)",
     "Expense Account\nJan 14 Passport photos $2.50\nPassport fee 10.00\nColombian visa 10.00\n"
     "Apr 7 Taxi and bus to airport (NY) 2.50\nBus + porter, Miami 1.60\nMeals 6.65",
     years_from_name(V1943_45), "EXPENSE ACCOUNT"),
    ("dated line items with amounts (1943-45 IMG_085)",
     "Nov. 1 Lunch and taxi at Panama $1.80\nDinner at Miami 2.25\nBus and taxi at 2.45\n$6.50\n"
     "Feb. 18 Entertainment 18.00\nAir mail postage 5.25\nHotel Granada 155.50\nVarious tips 3.50\n"
     "Laundry 2.45\nPanama loan 15.00\nVarious taxi fares 1.70\nLaundry 2.00",
     years_from_name(V1943_45), "ACCOUNT"),
    ("dated line items with amounts (1943-45 IMG_082)",
     "Oct. 22 Taxi and porter to Hotel Prado $2.00\nAuto getting schedule + ticket $4.00\n"
     "Hotel del Prado $18.00\nVarious tips $1.50\nBaggage to Hotel Miranda + tips $2.40\n"
     "Taxi getting schedule + reservations $1.40\nVarious taxi fares $2.00\nLaundry $2.00",
     years_from_name(V1943_45), "ACCOUNT"),
    ("the amounts on their own lines (1943-45 IMG_084)",
     "Sept 15\nAm, taxi, + porter at NY\n2.40\nOct 11\nHotel Citarum, Buenaventura\n6.50\n"
     "Am, taxi + porter at Miami\n1.30\nAir-mail postage\n3.15\nMeals\n5.75",
     years_from_name(V1943_45), "ACCOUNT"),
    ("the bank ledger under the bank's name (1943-45 IMG_081)",
     "Irving Trust Co.\nFeb 28 Balance 20778.21\nMar 1 Div. Duvee & Reynolds 25.00\n"
     "Tidewater Assoc. Oil 20.00\nVick Chemical 50.00\nWesson Oil & Snowdrift 50.00\nRail Electric 40.00",
     years_from_name(V1943_45), "ACCOUNT"),
]


@pytest.mark.parametrize("case,text,years,marker", ACCOUNT_PAGES, ids=[c[0] for c in ACCOUNT_PAGES])
def test_account_pages_stay_undated(case, text, years, marker):
    # In the run, the 1943-45 pages took their year from the dated page before them.
    finding = find_page_date(text, volume_years=years, previous=gregorian_to_jdn(1944, 10, 1),
                             volume_range=(gregorian_to_jdn(1943, 10, 17), gregorian_to_jdn(1945, 9, 22)))
    assert finding.date is None and finding.non_entry == marker, (case, finding)


DAYS_WITH_EXPENSES = [
    ("1927 IMG_008_part_1",
     "MONDAY, JANUARY 10, 1927\nWent in to Cali today. RR fare to Cali .70\nDrew $200 from bank. Auto .50\n"
     "Met Dr. Alberto Holguin. Telephone .70\nIn evening Dr. Guerrero called.\nArranged with him to return to\n"
     "Saturnia at $350 per month & board.\nTUESDAY, JANUARY 11, 1927\nRR fare .70\nAuto .60\nHotel 4.00\n"
     "Boy .50\nWEDNESDAY, JANUARY 12, 1927", [1927], "1927-01-10"),
    ("1931 IMG_045_part_2",
     "FRIDAY, SEPTEMBER 4, 1931\nOn board train\nBreakfast 1.25\nLunch 1.50\nDinner 2.00\nPorter 1.00\n"
     "Bed 50\nSATURDAY, SEPTEMBER 5, 1931\nArrived at New York at 6:30 AM", [1931], "1931-09-04"),
]


@pytest.mark.parametrize("case,text,years,iso", DAYS_WITH_EXPENSES, ids=[c[0] for c in DAYS_WITH_EXPENSES])
def test_a_diary_day_listing_its_expenses_is_still_an_entry(case, text, years, iso):
    """A day that lists what it cost names its weekday: an entry, not an account page."""
    finding = find_page_date(text, volume_years=years)
    assert finding.non_entry is None and finding.date.meta["converted_gregorian_iso"] == iso, case


def test_bank_balance_inside_an_entry_does_not_undate_it():
    """Only a page's FIRST line is an account title; under a heading it is a line of the entry."""
    date = find_page_date("MONDAY, JANUARY 1, 1940\nBank balance Irving Trust Co. $18182.75",
                          volume_years=[1940]).date
    assert date.meta["converted_gregorian_iso"] == "1940-01-01"


def test_sun_life_is_an_insurer_not_a_sunday():
    """28 Oct 1941 was a Tuesday: "Sun Life" read as Sunday flagged a conflict that was not there."""
    date = find_page_date("October 28 - Sun Life Assurance Co. of Canada, 1180 Raymond Blvd.,",
                          volume_years=[1941]).date
    assert date.meta["converted_gregorian_iso"] == "1941-10-28"
    assert "weekday_conflict" not in date.meta


def test_a_trailing_weekday_abbreviation_is_still_read():
    # 29 Nov 1914 was a Sunday; 28 Nov a Saturday, so "Sun" there is a conflict to flag.
    assert "weekday_conflict" not in find_page_date("Nov. 29 Sun.", volume_years=[1914]).date.meta
    assert "weekday_conflict" not in find_page_date("Nov. 29 Sun", volume_years=[1914]).date.meta
    assert "weekday_conflict" in find_page_date("Nov. 28 Sun", volume_years=[1914]).date.meta
