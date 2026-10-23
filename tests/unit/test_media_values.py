# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""A save writes each cue's stored media values from its library row (002 US6, FR-038 to FR-042).

The six tests FR-042 names, which close cuems-utils T039, plus the
item-assignment grep (FR-040, M11). Each builds a ``CuemsScript`` from
``tests/data/script_minimal_013.xml`` and saves it with the real
``CuemsDBProject.update`` against a temporary library whose ``Media`` rows
carry known values:

* ``file_video.ext`` (a movie): 1920x1080, 1000 bytes, md5 ``a`` * 32;
* ``file.ext`` (audio): 500 bytes, no md5 (unknown).

Values a setter accepts are set on the object through attribute assignment.
Values a setter refuses are put in the payload dict ``update`` receives, which
is where a client's arrive: ``CuemsScript.from_json`` stores them raw.
"""

from support.paths import DATA_DIR, PACKAGE_DIR, ROOT, SIBLINGS_DIR, SPECS_DIR
import json
import os
import re
from pathlib import Path

import pytest

from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia, database
from cuemseditor.CuemsDBProject import CuemsDBProject
from cuemsutils.cues import CuemsScript, CueList
from cuemsutils.cues.MediaCue import MediaCue
from cuemsutils.helpers import new_datetime, new_uuid

FIXTURE_013 = DATA_DIR / 'script_minimal_013.xml'
PACKAGE = PACKAGE_DIR
SCRIPT_ID = 'ddba3000-7894-4a60-a6c1-e73b9bbed8c0'
VIDEO_CUE = '1f301cf8-dd03-4b40-ac17-ef0e5e7988be'
AUDIO_CUE = 'bb391e70-e65e-47ca-8b29-5a7076bbd250'
OTHER_CUE = '96d6e5de-c29b-4ab2-b828-297d84293304'      # video, or "lighting" in that variant
VIDEO_MD5 = 'a' * 32
ROWS = {
    'file_video.ext': dict(media_type='MOVIE', duration='00:01:00.000',
                           pixel_width=1920, pixel_height=1080, file_size=1000, file_md5=VIDEO_MD5),
    'file.ext': dict(media_type='AUDIO', duration='00:01:00.000', file_size=500, file_md5=None),
}
STORED_KEYS = ('pixel_width', 'pixel_height', 'file_size', 'file_md5')


class MediaLib:
    def __init__(self, root):
        self.root = root
        self.script = os.path.join(root, 'projects', 'minimal', 'script.xml')


def write_script(path, other_class='video'):
    """The fixture, saved by the library as a current document (it loads clean).

    *other_class* re-classes cue ``96d6e5de``; ``lighting`` decodes as a bare
    ``MediaCue``.
    """
    script, _report = CuemsScript.load_with_report(str(FIXTURE_013))
    script.save(path)
    if other_class != 'video':
        text = Path(path).read_text(encoding='utf-8')
        head, tail = text.split(f'<id>{OTHER_CUE}</id>', 1)
        i = head.rindex('<Cue class="video">')
        head = head[:i] + f'<Cue class="{other_class}">' + head[i + len('<Cue class="video">'):]
        cue, rest = tail.split('</Cue>', 1)
        cue = re.sub(r'<opacity>[^<]*</opacity>', '', cue)    # a video cue's field only
        Path(path).write_text(head + f'<id>{OTHER_CUE}</id>' + cue + '</Cue>' + rest, encoding='utf-8')


def make_media_lib(root, rows=ROWS):
    for sub in ('media', 'trash/projects', 'trash/media', 'tmp', 'projects/minimal'):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    database.init(os.path.join(root, 'project-manager.db'))
    database.connect(reuse_if_open=True)
    database.create_tables([Project, Media, ProjectMedia], safe=True)
    Project.create(uuid=SCRIPT_ID, name='Test Script', unix_name='minimal',
                   created=new_datetime(), modified=new_datetime(), in_trash=False)
    for name, values in rows.items():
        Media.create(uuid=str(new_uuid()), name=name, unix_name=name, created=new_datetime(),
                     modified=new_datetime(), in_trash=False, **values)
    settings = get_settings()
    settings['library_path'] = root
    settings['tmp_path'] = os.path.join(root, 'tmp')
    ctx = MediaLib(root)
    ctx.project = CuemsDBProject(settings, database)
    write_script(ctx.script)
    return ctx


@pytest.fixture
def mlib(tmp_path):
    yield make_media_lib(str(tmp_path))
    database.close()


def cues(script):
    def walk(contents):
        for cue in contents or ():
            if isinstance(cue, CueList):
                yield from walk(cue.contents)
            else:
                yield cue
    return {str(cue.id): cue for cue in walk(script.cuelist.contents)}


def load(lib):
    return CuemsScript.load_with_report(lib.script)[0]


def wire(script):
    return json.loads(json.dumps(script.to_wire()))


def wire_media(data, cue_id):
    """The ``Media`` dict of cue *cue_id* in a wire payload."""
    def walk(contents):
        for item in contents:
            for key, cue in item.items():
                if key == 'CueList':
                    yield from walk(cue.get('contents') or [])
                elif isinstance(cue, dict) and cue.get('id') == cue_id:
                    yield cue['Media']
    return next(walk(data['CuemsScript']['CueList']['contents']))


def save(lib, data):
    lib.project.update(SCRIPT_ID, data)
    return cues(load(lib))


def stored(cue):
    media = cue['Media']
    return {key: media[key] for key in STORED_KEYS if key in media}


# ─── FR-042's six (red first: evidence/media-values-failing-first.txt) ───


def test_an_audio_cue_loses_pixel_size_and_a_video_cue_keeps_it(mlib):
    script = load(mlib)
    for cue_id in (AUDIO_CUE, VIDEO_CUE):
        media = cues(script)[cue_id]['Media']
        media.pixel_width = 640
        media.pixel_height = 480

    saved = save(mlib, wire(script))

    assert stored(saved[AUDIO_CUE]) == {'file_size': 500}
    assert stored(saved[VIDEO_CUE]) == {'pixel_width': 1920, 'pixel_height': 1080,
                                        'file_size': 1000, 'file_md5': VIDEO_MD5}


def test_an_unknown_class_media_cue_keeps_its_pixel_size(mlib):
    write_script(mlib.script, other_class='lighting')
    script = load(mlib)
    lighting = cues(script)[OTHER_CUE]
    assert type(lighting) is MediaCue
    lighting['Media'].pixel_width = 640
    lighting['Media'].pixel_height = 480

    saved = save(mlib, wire(script))

    assert type(saved[OTHER_CUE]) is MediaCue
    assert stored(saved[OTHER_CUE]) == {'pixel_width': 1920, 'pixel_height': 1080,
                                        'file_size': 1000, 'file_md5': VIDEO_MD5}


def test_an_uppercase_client_md5_is_stored_lowercase_and_the_save_succeeds(mlib):
    data = wire(load(mlib))
    wire_media(data, VIDEO_CUE)['file_md5'] = VIDEO_MD5.upper()

    saved = save(mlib, data)

    assert saved[VIDEO_CUE]['Media']['file_md5'] == VIDEO_MD5


@pytest.mark.parametrize('bad', ['z' * 32, 'abc', 'a' * 31, 'a' * 33])
def test_a_non_hex_or_wrong_length_md5_is_dropped_and_the_save_succeeds(mlib, bad):
    data = wire(load(mlib))
    wire_media(data, AUDIO_CUE)['file_md5'] = bad          # file.ext's row has no md5

    saved = save(mlib, data)

    assert 'file_md5' not in saved[AUDIO_CUE]['Media']


@pytest.mark.parametrize('bad', [0, 1.5, True])
def test_zero_float_and_bool_file_sizes_are_dropped_not_assigned(mlib, bad):
    data = wire(load(mlib))
    wire_media(data, AUDIO_CUE)['file_size'] = bad

    saved = save(mlib, data)

    assert saved[AUDIO_CUE]['Media']['file_size'] == 500   # the row's, never the client's


def test_a_cleared_value_is_absent_not_zero_not_null(mlib):
    script = load(mlib)
    cues(script)[AUDIO_CUE]['Media'].file_md5 = 'c' * 32    # the row knows no md5

    save(mlib, wire(script))

    reloaded = load(mlib)
    media = cues(reloaded)[AUDIO_CUE]['Media']
    assert 'file_md5' not in media
    assert 'file_md5' not in wire_media(wire(reloaded), AUDIO_CUE)


# ─── FR-040, M11: no item assignment on the stored keys ──────────────────


ITEM_ASSIGNMENT = (
    re.compile(r"""\[['"](pixel_width|pixel_height|file_size|file_md5)['"]\]\s*=(?!=)"""),
    re.compile(r"""del \w+\[['"](pixel_width|pixel_height|file_size|file_md5)"""),
    re.compile(r"""\.pop\(['"](pixel_width|pixel_height|file_size|file_md5)"""),
)


def test_no_item_assignment_on_stored_media_keys():
    offenders = [
        f'{path.name}:{number}: {line.strip()}'
        for path in sorted(PACKAGE.glob('*.py'))
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
        if any(pattern.search(line) for pattern in ITEM_ASSIGNMENT)
    ]
    assert offenders == []
