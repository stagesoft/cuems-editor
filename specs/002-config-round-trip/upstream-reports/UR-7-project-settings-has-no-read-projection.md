<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-7 — `project_settings` has no public read projection

**From** cuems-editor 002 (T045), 2026-10-12. **To** `cuems-utils`. cuemsutils `0.1.0rc16` from
`../cuems-utils` @ `cdb3bef` on `014-xs-boolean-and-media-elements` (`src/` unchanged since
`b2ea09a`). This is gate **G2** of the `xml-refactor-merge-candidate` tag; the requirement is
already stated in `cuems-utils` `specs/planning/upcoming-feature-requirements-2026-10-02.md` §0a G2,
and this file is the report that subsection waits for.

**Observed.**

- `_PROJECTABLE_SECTIONS` (`src/cuemsutils/tools/ConfigManager.py:166`) lists `project_mappings` and
  not `project_settings`, so `ConfigManager.to_wire('project_settings')` raises `ValueError`
  ("unknown configuration section").
- `load_project_settings` keeps the decoded document on the private `_project_settings_document`
  (`:531`). No public property exposes it. `project_conf` is `conf.get_dict()`, which the same
  method's comment says is always `{}` for this schema.
- So `from_json(SchemaName.PROJECT_SETTINGS, …)` ingests a document that no public call can
  produce. It is the read-side mirror of `cuems-editor` UR-5.

**Why the editor needs it.** `config_load` (002 FR-012, FR-018) serves each configuration document
as the file holds it, projected by `ConfigManager.to_wire(section)` on a freshly loaded manager, so
that the UI edits the real values and `config_save` writes the whole document back (002 S3, S4).
`settings`, `network_map` and `project_mappings` all project. `project_settings` does not, so its
editing form has nothing to show.

**Workaround.** None. `tests/test_public_surface.py` forbids reaching `_project_settings_document`,
and projecting the document in the editor would be a second projection, which constitution V
forbids. `config_load('project_settings')` is refused with the error frame, naming this report:

```text
{"type": "error", "action": "config_load", "value": "config_load: project_settings has no public
 read projection in cuemsutils (cuems-editor UR-7); it cannot be loaded yet"}
```

`config_save('project_settings')` works today over an existing file, with `base_revision` from the
file's md5 (a project's first save is gate G1, `cuems-editor` UR-6).

**Expected** (§0a G2's shape):

- a public `project_settings` (property or section), projected through the same `to_wire()` body as
  the other sections;
- `'project_settings'` added to `_PROJECTABLE_SECTIONS`;
- a library test: `to_wire('project_settings')` → `from_json` → `save` → reload compares equal.

For a project with no `settings.xml`, `load_project_settings` keeps defaults. Projecting those is
fine: the editor reports `exists` itself, from `project_path`'s `FileNotFoundError`.

**The editor test that flips.**
`tests/test_upstream_gates.py::test_config_load_project_settings_round_trips`, a
`xfail(strict=True, raises=AssertionError)` that asserts `config_load` returns `exists: true` and the
document that was written. When the library lands the projection, the editor removes
`project_settings` from `CONFIG_LOAD_REFUSED` and gives it a `CONFIG_LOAD_STEPS` entry
(`load_project_settings(uname)`), both in `src/cuemseditor/CuemsWsUser.py`. The test then XPASSes,
which fails the suite until its marker is removed (002 S6).
