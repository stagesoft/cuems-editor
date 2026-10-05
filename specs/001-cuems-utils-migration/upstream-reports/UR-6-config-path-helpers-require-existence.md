<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-6 — `conf_path`/`project_path` refuse the file a first save would create

**From** cuems-editor 001 (T059 follow-up), 2026-10-05. cuemsutils `0.1.0rc16` @ `014-xs-boolean-and-media-elements` (`b8b44e7`), which includes `429f8d2` (UR-5's fix).

**Observed.** `ConfigManager.conf_path(file_name)` and `ConfigManager.project_path(project_uname, file_name)`
(`src/cuemsutils/tools/ConfigBase.py:147`, `src/cuemsutils/tools/ConfigManager.py:905`) both check
existence before returning a path, and raise `FileNotFoundError` when the file is not already on
disk:

```python
def project_path(self, project_uname: str, file_name: str) -> str:
    project_path = path.join(self.library_path, 'projects', project_uname, file_name)
    if not path.exists(project_path):
        raise FileNotFoundError(f'Project file {project_path} not found')
    return project_path
```

`save_settings`/`save_network_map`/`save_project_settings`/`save_project_mappings` all default
their `path` argument to exactly this call when the caller does not supply one — which is the
common case, and the one `ConfigManager.from_json`'s own docstring demonstrates:

```python
manager  = ConfigManager(load_all=False)
document = manager.from_json(SchemaName.SETTINGS, payload)
document.save(manager.conf_path('settings.xml'))   # raises if settings.xml never existed
```

But a project's `settings.xml`/`mappings.xml` not existing is the *ordinary* state, not an edge
case: `load_project_settings` explicitly tolerates it (`except FileNotFoundError: ... "Keeping
default settings"`), and this library's own test suite documents the same limitation rather than
asserting around it —
`../cuems-utils/tests/integration/test_config_manager_save_accessors.py:59-65`:

> `project_config_manager` with a real project directory behind it, so `load_project_config`/
> `save_project_settings`/`save_project_mappings` have something concrete to round-trip rather
> than falling back to defaults (`project_path` raising `FileNotFoundError`, per
> `ConfigManager.load_project_mappings`'s except branch).

That fixture works around it with `monkeypatch.setattr(config_manager, "project_path", _project_path)`
— replacing the method itself, because there is no supported way to get a write target that
tolerates a missing file. `document.save(path)` does not require `path` to pre-exist (`write_tree`
only needs the parent directory — confirmed by writing to a path that never existed and getting a
correct file back), so the limitation is entirely in `conf_path`/`project_path`, not in `.save()`.

**Why the editor needs it.** `config_save` (FR-045) now builds `project_mappings`/`project_settings`
documents with `ConfigManager.from_json` (UR-5) and a resolved `unix_name`
(`CuemsDBProject.get_project_unix_name`, cuems-editor's own lookup — not a library concern). The
only thing standing between that and a working save is resolving the write target, and the public
way to do that — `project_path` — refuses to for exactly the case this feature exists to enable: a
project whose config has never been customised before. The editor does not hand-roll
`os.path.join(library_path, 'projects', project_uname, file_name)` itself, because that duplicates a
convention this library already owns and encapsulates — and this report exists so the editor does
not have to.

**Workaround taken.** None viable without either reimplementing the path convention here or
monkeypatching the library the way its own tests do. `config_save` of `project_mappings`/
`project_settings` resolves the project and builds the document, then calls the real
`project_path`/`.save()` and lets `FileNotFoundError` surface as the ordinary error frame. A
project's *first* `config_save` of either domain fails until this is fixed upstream.
`tests/test_schema_descriptor.py::test_config_save_of_project_settings_fails_before_the_file_exists_pending_ur6`
pins today's error so it is easy to find and flip into a round-trip assertion once the library
offers a fix; `test_config_save_of_project_settings_persists_once_the_file_exists` proves the rest
of the wiring (project_uuid → unix_name → `from_json` → `.save`) already works when the file does
exist.

**Expected.** Either of these closes the gap, symmetric with how `from_json` itself was specified:

- An existence-tolerant mode on the existing calls, e.g. `conf_path(file_name, must_exist=False)` /
  `project_path(project_uname, file_name, must_exist=False)`, returning the canonical path
  regardless of whether it exists yet; or
- A single call that does the whole round trip for a config domain — build from JSON, resolve the
  write target (tolerating a first save), and persist — so `from_json`'s caller never touches
  `conf_path`/`project_path` at all for this purpose.

Either form should leave the *existing* behaviour of `conf_path`/`project_path` (and the default
`path` argument on each `save_*`) unchanged for every other caller — this report asks for an
addition, not a loosening of the current check, since other callers (`load_*`) rely on it to report
a missing file as a missing file.
