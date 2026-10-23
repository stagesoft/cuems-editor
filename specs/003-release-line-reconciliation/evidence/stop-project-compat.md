# `stop_project` compatibility (T020–T022)

Tests: `tests/test_stop_project_save.py` (4 cases: target `None`, `""`, absent; a leftover target) and
`tests/test_validate_media_cues.py::test_the_librarys_media_error_reaches_the_client_unprefixed` (utils 017 §1).

| Library | Result | Commit |
|---|---|---|
| cuemsutils @ the candidate tag | the 5 cases are `xfail` (strict): `stop_project` is not in `script.xsd`; `get_media` raises `KeyError('file_name')` | `4b336cd` |
| cuemsutils @ the utils `feat/xml-refactor` head | all 5 **pass** (`--runxfail`), i.e. XPASS-strict without the markers: the save/reopen round trip works and a leftover target is refused with `project_action_takes_no_target` | `387598e` |

Measured 2026-10-23. Conclusion: the editor is compatible with the library that will be re-cut. The markers come off
when the `xml-refactor-merge-candidate` tag of cuems-utils is re-cut to carry the value (a maintainer act); at that point
the suite goes red (XPASS-strict) until the five markers are removed. Until then they stay, and the tag message lists
the dependency (FR-032).

X-4 (absent stored media values read as missing, attribute `None`, not `Unset`) is asserted in
`tests/test_media_staleness.py` (T021).
