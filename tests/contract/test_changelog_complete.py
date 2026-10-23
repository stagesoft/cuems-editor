# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every build that shipped is in the stable changelogs (003, FR-025 to FR-027).

Rule 4 of the coordinated release (merge before bump) is only worth its name if a
later merge of the release line cannot drop a build without a test going red. The
released builds are listed in ``tests/data/released-builds.txt``; this checks, for
each, ``debian/changelog`` (one header per build) and ``CHANGELOG.md`` (named in a
``<!-- source: … -->`` marker or inline), then the version sites, and, where the
release tags exist locally (CI fetches them), that each entry is byte-identical to
the one at its tag.
"""
from support.paths import DATA_DIR, PACKAGE_DIR, ROOT, SIBLINGS_DIR, SPECS_DIR
import pathlib
import re
import subprocess

import pytest

MANIFEST = DATA_DIR / 'released-builds.txt'
HEADER = re.compile(r'^cuems-editor \((?P<version>[^)]+)\) ', re.MULTILINE)


def _manifest():
    released, excluded = [], {}
    for raw in MANIFEST.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('excluded:'):
            version, _, reason = line[len('excluded:'):].partition('|')
            excluded[version.strip()] = reason.strip()
        else:
            released.append(line)
    return released, excluded


RELEASED, EXCLUDED = _manifest()


def _changelog():
    return (ROOT / 'debian' / 'changelog').read_text(encoding='utf-8')


def _entries(text):
    """{version: entry text from its header through its trailer line}."""
    starts = [(m.start(), m.group('version')) for m in HEADER.finditer(text)]
    out = {}
    for i, (start, version) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        out[version] = text[start:end].rstrip('\n') + '\n'
    return out


def _pyproject_version():
    return re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / 'pyproject.toml').read_text(encoding='utf-8'),
                     re.MULTILINE).group(1)


def test_the_manifest_is_read():
    assert RELEASED and RELEASED == sorted(set(RELEASED), key=RELEASED.index)
    assert '0.1.0rc1-5+nodeadopt2' in EXCLUDED and all(EXCLUDED.values())


@pytest.mark.parametrize('version', RELEASED)
def test_every_released_build_is_a_debian_changelog_entry(version):
    assert version in _entries(_changelog())


@pytest.mark.parametrize('version', RELEASED)
def test_every_released_build_is_named_in_the_upstream_changelog(version):
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert re.search(rf'(?<![\w.+-]){re.escape(version)}(?![\w.+-])', text), version


@pytest.mark.parametrize('version', sorted(EXCLUDED))
def test_a_rig_build_is_not_a_changelog_entry(version):
    assert version not in _entries(_changelog())


def test_the_top_entry_matches_the_version_sites():
    import cuemseditor
    version = _pyproject_version()
    entries = list(_entries(_changelog()))
    assert entries[0] == f'{version}-1'
    assert cuemseditor.__version__ == version
    top = re.search(r'^## (\S+)', (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'), re.MULTILINE).group(1)
    assert top == version


def test_the_top_entry_no_longer_says_it_is_unreconciled():
    top = next(iter(_entries(_changelog()).values()))
    assert 'NOT YET RECONCILED' not in top and 'Do not publish until' not in top


def _at_tag(version):
    result = subprocess.run(['git', 'show', f'v{version}:debian/changelog'], cwd=ROOT,
                            capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


@pytest.mark.parametrize('version', RELEASED)
def test_a_released_entry_is_byte_identical_to_the_one_at_its_tag(version):
    released = _at_tag(version)
    if released is None:
        pytest.skip(f'no local tag v{version} (fetch tags: CI does)')
    assert _entries(_changelog())[version] == _entries(released)[version]
