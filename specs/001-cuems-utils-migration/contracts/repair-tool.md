<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — `cuems-editor-repair-durations`

The tool exists to correct durations a historical `get_duration` bug stored short, and to say
which scripts still need an operator save. It is not a document converter. After this feature
the only document rewriter in the ecosystem is `cuems-convert-documents`.

## What it writes

| Target | Behaviour |
|---|---|
| `project-manager.db` | Pass A. Re-probe media with ffprobe. Dry-run is the default. `--apply` writes, and writes only after a backup of the database |
| script XML | **never**, under any flag |
| `trash/`, script backups beside the XML | not by this tool. The editor's save path preserves a repaired original (see [ws-messages.md](ws-messages.md)) |

Removed: `pass_b_xml`, the XML backup directory it created, and `--xml-only` as a mode that
writes scripts. `--db-only` becomes meaningless and is removed rather than left as a no-op
alias. `--apply`, `--skip-trash`, `--library-path`, `--database-name`, and `--backup-dir` stay
for the database.

## What it reports

Per media row, after pass A: corrected, unchanged, or skipped (missing file, probe failure).
Per project script, after a public load:

| Outcome | Meaning |
|---|---|
| *needs a save* | at least one media duration in the script differs from the corrected database value. The line names the project, the media, the script value, and the database value |
| unchanged | every comparable duration matches |
| `SKIPPED_INVALID` | the script could not be loaded. The reason is the exception text. The project is not dropped from the report |

Comparison uses `CTimecode`, not a local regex. A structured duration (`{"CTimecode": ...}` on
the wire, `CTimecode` on the object) that differs from the database is a mismatch. The test
that pins this fails against the pre-migration guard, which calls `TIMECODE_SHAPE.match` on a
string and therefore never sees a dict.

The tool does not call `cuems-convert-documents` and does not save the script it loaded. A
version-1 script that the library converts in memory is reported from the in-memory object; the
file's bytes stay as they were. If the in-memory durations still differ from the database, the
project is *needs a save*. The conversion itself is not this tool's write.

## Help text

The module docstring and `--help` say that script files change only when an operator opens the
project and saves it, and that until that save the engine plays the file on disk. The same
sentence is a `CLAUDE.md` field note (FR-027a).

## Tests

`tests/test_repair_durations.py` keeps the pass A cases (dry-run, `--apply` and backup,
idempotence, trash, missing database). Pass B assertions (XML no longer contains
`00:00:00.000` because the tool wrote it) are retired in the test module's header comment,
with this contract as the reason. The replacement assertion: after `--apply`, every `script.xml`
checksum is unchanged, and the *needs a save* list matches the fixture.

The fixture set is the one already under `tests/` for this module, named in the test. A script
the tool cannot read is the existing bad-XML case, expected `SKIPPED_INVALID`, and the other
project in that run is still corrected in the database.
