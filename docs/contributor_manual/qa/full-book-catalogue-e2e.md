(AI generated. Not reviewed.)

# Full-Book Catalogue + KG E2E

Issue: #1317

Run only when Daniel's local fixture is available:

```bash
FICHERO_RUN_FULL_BOOK_E2E=1 \
PYTHONPATH=fichero-server/src \
~/.venv/bin/python -m pytest \
  fichero-server/tests/integration/test_full_book_catalogue_e2e.py::test_tubb2020shift_catalogue_populates_kg -q
```

Override the fixture path with `FICHERO_FULL_BOOK_E2E_PDF=/path/to/book.pdf`.

The test ingests `tubb2020shift.pdf`, runs the Catalogue workflow, then verifies:

- KG entities exist for the document/page scope.
- Source-backed claims exist.
- At least one claim has source page labels for OntologyBrowser click-through.
- Citation lookup does not 500.
