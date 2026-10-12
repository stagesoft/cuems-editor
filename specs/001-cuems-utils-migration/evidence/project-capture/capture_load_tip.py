# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture the ``project`` frame at the tip, the way ``send_project`` builds it.

Supersedes ``capture_load.py`` (beside this file) **at the tip only**: that
script recorded the procedure that produced the rc14 frame at editor
``e05f4e7`` and stays byte-unchanged as that record (002 FR-030, M6). Since
cuemsutils 013, ``CuemsDBProject.load_xml`` returns ``(CuemsScript,
LoadReport)``, and the frame's value is ``script.to_wire()``.

Usage (quickstart §5)::

    PYTHONPATH=src $E/bin/python -P specs/001-cuems-utils-migration/evidence/project-capture/capture_load_tip.py \\
        > specs/002-config-round-trip/evidence/project-frame-tip.json

(``cuemseditor`` is not installed in the hatch environment, so ``-I``, which
ignores ``PYTHONPATH``, cannot import it; ``-P`` keeps this directory off
``sys.path``.)

The fixture defaults to ``tests/fixtures/script_minimal_013.xml``; a path
argument replaces it. Like ``capture_load.py``, it loads from a temporary
library and reports on stderr that the file was not written.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

import cuemsutils
from cuemseditor.CuemsDBProject import CuemsDBProject

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, '..', '..', '..', '..', 'tests', 'fixtures', 'script_minimal_013.xml')

fixture = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
lib = tempfile.mkdtemp()
os.makedirs(os.path.join(lib, 'projects', 'p'))
dst = os.path.join(lib, 'projects', 'p', 'script.xml')
shutil.copy(fixture, dst)
p = CuemsDBProject.__new__(CuemsDBProject)
p.projects_path = os.path.join(lib, 'projects'); p.script_file_name = 'script.xml'; p.script_schema_name = 'script'
before = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
script, report = p.load_xml('p')
after = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
frame = json.dumps({"type": "project", "value": script.to_wire()})
print(json.dumps({"lib": cuemsutils.__version__, "file": cuemsutils.__file__, "fixture": fixture,
                  "outcome": report.outcome.value, "before": before, "after": after}), file=sys.stderr)
shutil.rmtree(lib)
print(frame)
