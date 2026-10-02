# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The editor reaches cuemsutils through public paths only (FR-005, FR-006).

``cuemsutils.xml`` and ``cuemsutils.config`` are internal (``__all__ == []``),
and ``create_script`` / ``timeoutloop`` are gone upstream. This scans the
shipped package's source text, so it does not need ``cuemseditor`` to import to
decide that a forbidden name is present. Contract:
specs/001-cuems-utils-migration/contracts/public-surface.md.

This file and retired-test records are the only places under ``tests/`` that
spell the banned names.
"""

import ast
import importlib
import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "cuemseditor"
SERVER = PACKAGE / "CuemsWsServer.py"

# Import statements only (line start + indentation), so prose naming a path in
# a docstring does not trip the rule.
INTERNAL_IMPORT = re.compile(
    r"^\s*(?:from\s+cuemsutils\.(?:xml|config|create_script|timeoutloop)\b"
    r"|import\s+cuemsutils\.(?:xml|config|create_script|timeoutloop)\b"
    r"|from\s+cuemsutils\s+import\s+.*\b(?:xml|config|create_script|timeoutloop)\b)",
    re.MULTILINE,
)
ANY_CUEMSUTILS_IMPORT = re.compile(r"^\s*(?:from|import)\s+cuemsutils\b", re.MULTILINE)

# Anywhere in the source text, comments and docstrings included.
BANNED_SUBSTRINGS = (
    "CuemsParser",
    "XmlReaderWriter",
    "create_script",
    "get_nodes_by_adoption",
    "_select_adopted",
    "def partition_by_adoption",
    "CUE_TYPES",
    "'AudioCue' in",
    '"AudioCue" in',
    "'VideoCue' in",
    '"VideoCue" in',
    "'DmxCue' in",
    '"DmxCue" in',
    "node_type",
    "NodeType.",
)

PARTITION_IMPORT = "from cuemsutils.tools.NodeList import partition_by_adoption"
PARTITION_USE = re.compile(r"partition_by_adoption")
PARTITION_CALL = re.compile(r"(?<![\w.])partition_by_adoption\(")

# (file, name) pairs imported from a public module but defined under
# cuemsutils.xml / cuemsutils.config. One is carried, to cuems-utils 014
# (plan.md Complexity Tracking). A second one fails.
CARRIED_EXCEPTIONS = {("cli.py", "ProjectMappings")}
# Published by cuems-utils 013 from a public module. The function object is
# still defined in cuemsutils.xml, which is what the module check would see.
PUBLISHED_REEXPORTS = {("cuemsutils.tools.NodeList", "partition_by_adoption")}


def _modules():
    return sorted(PACKAGE.rglob("*.py"))


def _where(module, text, offset):
    return f"{module.relative_to(PACKAGE.parent)}:{text.count(chr(10), 0, offset) + 1}"


def _offenders(pattern, modules):
    found = []
    for module in modules:
        text = module.read_text(encoding="utf-8")
        found += [_where(module, text, m.start()) for m in pattern.finditer(text)]
    return found


def test_the_scan_is_not_vacuous():
    """A rename or a wrong root must not turn every rule silently green."""
    modules = _modules()
    assert modules, f"no modules found under {PACKAGE}"
    assert _offenders(ANY_CUEMSUTILS_IMPORT, modules), (
        f"no cuemsutils import found under {PACKAGE}: the scan is looking in the wrong place"
    )


def test_no_internal_or_removed_cuemsutils_import():
    offenders = _offenders(INTERNAL_IMPORT, _modules())
    assert not offenders, (
        "imports of cuemsutils.xml / .config / .create_script / .timeoutloop: "
        f"{offenders}. Use CuemsScript and ConfigManager instead."
    )


@pytest.mark.parametrize("banned", BANNED_SUBSTRINGS)
def test_banned_name_is_absent(banned):
    offenders = _offenders(re.compile(re.escape(banned)), _modules())
    assert not offenders, f"{banned!r} in src/: {offenders}"


def test_partition_by_adoption_is_only_the_published_import_and_its_calls():
    offenders = []
    for module in _modules():
        for number, line in enumerate(module.read_text(encoding="utf-8").splitlines(), 1):
            if not PARTITION_USE.search(line):
                continue
            if line.strip() == PARTITION_IMPORT:
                continue
            uses = len(PARTITION_USE.findall(line))
            if uses == len(PARTITION_CALL.findall(line)) and not line.lstrip().startswith("#"):
                continue
            offenders.append(f"{module.relative_to(PACKAGE.parent)}:{number}: {line.strip()}")
    assert not offenders, f"partition_by_adoption used other than import + call: {offenders}"


def test_the_server_imports_the_published_partition():
    """Red until T036. The pinned 013 commit publishes it; the editor calls it."""
    assert PARTITION_IMPORT in SERVER.read_text(encoding="utf-8").splitlines()


def _imported_names(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "cuemsutils":
            for alias in node.names:
                yield node.module, alias.name


def test_no_internal_class_reached_through_a_public_module():
    """``ProjectMappings`` via ``ConfigManager``'s namespace is still cuemsutils.xml.

    The census regex cannot see that, so resolve each imported name and ask
    where it is defined. Imports cuemsutils, not cuemseditor.
    """
    offenders, carried_seen = [], set()
    for module in _modules():
        for source, name in _imported_names(module):
            if name == "*":
                continue
            obj = getattr(importlib.import_module(source), name, None)
            if obj is None or isinstance(obj, type(re)):
                continue
            defined_in = getattr(obj, "__module__", "") or ""
            if not defined_in.startswith(("cuemsutils.xml", "cuemsutils.config")):
                continue
            if (source, name) in PUBLISHED_REEXPORTS:
                continue
            if (module.name, name) in CARRIED_EXCEPTIONS:
                carried_seen.add((module.name, name))
                continue
            offenders.append(f"{module.relative_to(PACKAGE.parent)}: {name} from {source} (defined in {defined_in})")
    assert not offenders, f"internal classes imported through a public module: {offenders}"
    # The exception is carried, not permanent: once 014 removes it, drop it here.
    assert carried_seen == CARRIED_EXCEPTIONS, (
        f"carried exception no longer present ({CARRIED_EXCEPTIONS - carried_seen}); remove it from this test"
    )
