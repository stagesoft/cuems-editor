# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""One written statement of payload version 1, with no live string booleans (002 US3, FR-001 to FR-004).

Version 1 never shipped, so it is restated, not bumped, as the merge-candidate
wire: every boolean on it is a JSON true / false. A section of
``tests/ws-command-responses.txt`` that describes a live frame must not say
``"True"`` / ``"False"``. The retired ``initial_template`` section keeps its
delta list, as history.

Sections are split at headings: an unindented line with a blank line (or the
start of the file) before it and a blank line after it.
"""

import os
import re

RESPONSES = os.path.join(os.path.dirname(__file__), 'ws-command-responses.txt')
RETIRED = 'initial_template (retired at payload version 1)'
STRING_BOOLEANS = ('"True"', '"False"', "'True'", "'False'")


def _lines():
    with open(RESPONSES, encoding='utf-8') as fh:
        return fh.read().splitlines()


def _sections():
    """``{heading: [lines]}``; the command table before the first heading is ``''``."""
    lines = _lines()
    sections, heading = {'': []}, ''
    for i, line in enumerate(lines):
        before = lines[i - 1] if i else ''
        after = lines[i + 1] if i + 1 < len(lines) else ''
        if line.strip() and not line[0].isspace() and not before.strip() and not after.strip():
            heading = line.strip()
            sections.setdefault(heading, [])
            continue
        sections[heading].append(line)
    return sections


def _paragraph(starting):
    """The paragraph that starts with *starting*, its lines joined by single spaces."""
    lines = _lines()
    start = next(i for i, line in enumerate(lines) if line.startswith(starting))
    end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
    return re.sub(r'\s+', ' ', ' '.join(lines[start:end]))


def test_the_split_finds_the_live_and_retired_sections():
    sections = _sections()
    assert RETIRED in sections
    assert 'project (reply to project_load)' in sections
    assert 'Nodes: adoption' in sections


def test_no_live_frame_section_says_string_booleans():
    offenders = [
        (heading or '<command table>', line.strip())
        for heading, lines in _sections().items() if heading != RETIRED
        for line in lines if any(form in line for form in STRING_BOOLEANS)
    ]
    assert offenders == []


def test_version_1_is_restated_with_json_booleans():
    row = _paragraph('payload_version 1:')
    assert 'restated' in row
    assert 'JSON true / false' in row
    assert 'rather than bumped' in row
