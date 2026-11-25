# Focused CI checks

`ci/checks.py` loads application models and existing code under an explicit synthetic
settings module. It forces an in-memory SQLite database, local file storage, memory
queues/caches and an in-memory email backend. It clears external-provider credentials
and blocks socket connections before Django initializes. No payment, email, bot,
OCR-model download, live database or deployment operation is performed.

The existing tests selected here are:

- `core.tests.test_utils_fees`
- `core.tests.test_utils_pdf`
- `core.tests.test_validators`
- `booking.tests.test_settings`

These are focused source checks, not full PostgreSQL, external-provider, OCR-model,
browser or production acceptance. PostgreSQL-specific constraints and concurrency
need their own isolated integration environment. Existing test assertions are not
modified or skipped by this setup.

The GitHub workflow also checks Python syntax. It does not deploy or use repository secrets. A failing check remains a failing
job; no passing badge or coverage percentage is asserted by this document.

The Linux runner installs FreeType and JPEG development headers before the existing
Python requirements. The pinned xhtml2pdf dependency builds ReportLab 3.x from
source on Python 3.12; its native build requires those headers. This does not change
application dependency pins or the project's Python version.

The dependency build explicitly uses `-std=gnu17`: ReportLab 3.x contains C
identifiers that conflict with the newer GNU23 default. This follows the
[GCC compatibility guidance](https://gcc.gnu.org/gcc-15/porting_to.html#c23)
and does not disable a test, renderer extension or compiler diagnostic.
