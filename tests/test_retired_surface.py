# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``src/`` carries none of the surface the xml-refactor retired (003, FR-022, FR-023).

The release line's code brings several names back: a hand-rolled script
writer on ``XmlReaderWriter`` (the library's ``CuemsScript.save`` already
writes atomically), ``CuemsParser``, the dangling-target walk keyed on a cue
type list (CLAUDE.md: it nulled valid targets after cuems-utils 013), and a
second reader of the script on ``xml.etree`` (002 M10: one reader, the
library's object load). A merge that brings one back must fail here.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / 'src' / 'cuemseditor'

FORBIDDEN = {
    'XmlReaderWriter': 'constitution V: cuemsutils.xml is internal; CuemsScript.save writes atomically',
    'CuemsParser': 'constitution V: removed entry point; load through CuemsScript.load_with_report',
    'CUE_TYPES': 'CLAUDE.md: no walk keyed on cue names (hardware cues are Cue with class)',
    '_clean_dangling_targets': 'the library repairs target and refuses action_target (001)',
    'xml.etree': '002 M10: no second script reader',
    'ElementTree': '002 M10: no second script reader',
}


def _sources():
    return sorted(SRC.glob('*.py'))


def test_the_walk_found_the_sources():
    assert len(_sources()) > 10


def test_no_retired_name_is_used_in_src():
    hits = []
    for path in _sources():
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            for name, why in FORBIDDEN.items():
                if re.search(re.escape(name), line):
                    hits.append(f'{path.name}:{number}: {name} ({why})')
    assert hits == []
