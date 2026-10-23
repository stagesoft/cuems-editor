# Bookworm build (T044) — 2026-10-23

`bash tests/packaging/bookworm-build.sh` (an unprivileged bookworm chroot, `mmdebstrap --mode=unshare`; never `debuild` on the
trixie host). Raw evidence below, as the script wrote it. Note: the script is bash (`sh` fails with "Bad substitution").

| Check | Result |
|---|---|
| `Version` | `0.1.1-1` |
| `Depends` | `cuems-utils (>= 0.1.1), cuems-utils (<< 0.1.2~), cuems-common (>= 1.3.1~), python3 (>= 3.11)` (rows 11–13) |
| venv interpreter (`pyvenv.cfg`) | `home = /usr/bin`, chroot `python3` is 3.11.2 |
| `dpkg -c cuems-editor_0.1.1-1_all.deb \| grep -ci CACHEDIR` | **0**: the `CACHEDIR.TAG` strip in `debian/rules` works (row 6) |
| cuemsutils used for the wheel | `cuemsutils-0.1.1` built from the sibling checkout at `387598e` (the library head, not the tag: the script builds `../cuems-utils` as it stands) |
| editor commit | `2b46c39` (the feature branch at that moment) |

## Finding (pre-existing, not changed here)

The package ships only `cuems-editor` and `cuems-editor-manual` in `/usr/lib/cuems/bin/`: the whitelist in
`debian/rules` (`! -name "cuems-editor" ! -name "cuems-editor-manual"`) deletes the third console script,
`cuems-editor-repair-durations`, which `pyproject.toml` declares and CLAUDE.md documents. The same line is in `a2431f0` and in
`origin/debian/bookworm`, so no released build ever shipped the repair tool in its venv either. Adding it is a packaging
change (a new file in the `.deb`), outside this feature's "no new behaviour"; recorded for the maintainer.

## Raw
```
# T044 — cuems-editor built inside an unprivileged bookworm chroot (mmdebstrap --mode=unshare).
# Script: tests/packaging/bookworm-build.sh. Not debuild on the trixie host.
date: 2026-10-23T09:47:46+02:00
host: Debian GNU/Linux 13 (trixie), mmdebstrap 1.5.7
editor: 2b46c39, version 0.1.1-1
cuemsutils wheel: cuemsutils-0.1.1-py3-none-any.whl from ../cuems-utils @ 387598e

## chroot
os: Debian GNU/Linux 12 (bookworm)
python3: /usr/bin/python3 -> /usr/bin/python3.11 Python 3.11.2
dh-virtualenv 1.2.2-1.3
debhelper 13.11.4

## result
pass1 OK
build OK

## pyvenv.cfg of the build venv (pass 1; debian/rules removes it from the package)
home = /usr/bin
implementation = CPython
version_info = 3.11.2.final.0
virtualenv = 20.17.1+ds
include-system-site-packages = true
base-prefix = /usr
base-exec-prefix = /usr
base-executable = /usr/bin/python3

## the .deb
cuems-editor_0.1.1-1_all.deb  sha256 bbc65ddcca8159014c1c5b4542302705e2b182bee3b80e418d6243d984aae9e0
Package: cuems-editor
Version: 0.1.1-1
Architecture: all
Depends: cuems-utils (>= 0.1.1), cuems-utils (<< 0.1.2~), cuems-common (>= 1.3.1~), python3 (>= 3.11)

### contents (site-packages and bin only)
./usr/lib/cuems/bin/
./usr/lib/cuems/bin/cuems-editor
./usr/lib/cuems/bin/cuems-editor-manual
./usr/lib/cuems/lib/python3.11/site-packages/cuemseditor/
./usr/lib/cuems/lib/python3.11/site-packages/cuemseditor-0.1.1.dist-info/

## checks
pyvenv.cfg: home = /usr/bin
python3: /usr/bin/python3 -> /usr/bin/python3.11 Python 3.11.2
```
