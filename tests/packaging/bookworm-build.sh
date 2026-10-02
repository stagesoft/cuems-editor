#!/bin/bash
# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
#
# bookworm-build.sh — build the cuems-editor .deb inside an unprivileged bookworm
# chroot (001-cuems-utils-migration, T044, contracts/package-relations.md).
#
# A host `debuild` on a Debian 13 development machine targets trixie, and
# dh-virtualenv bakes whatever python3 it finds into the venv. The package is
# for bookworm controllers, so it is built in bookworm:
#
#   mmdebstrap --mode=unshare --variant=apt — a user-namespace chroot built as
#   the calling user, thrown away afterwards (target /dev/null). Same approach
#   as ../cuems-nodeconf/tests/packaging/release-gate-demo.sh.
#
# cuemsutils >= 0.1.0rc16 is not on PyPI (it stops at 0.1.0rc14), so a wheel is
# built from the sibling checkout and offered to dh-virtualenv's pip through
# PIP_FIND_LINKS (dh-virtualenv passes os.environ to pip unchanged; see the
# nodeconf script for the measurement). debian/rules is not edited.
#
# debian/rules deletes the venv's pyvenv.cfg from the package (cuems-utils owns
# /usr/lib/cuems). To check which interpreter the venv was made from, the build
# first runs dh up to dh_virtualenv and copies that pyvenv.cfg out, then cleans
# and runs the real dpkg-buildpackage.
#
# Usage:  tests/packaging/bookworm-build.sh
# Env:    WORK=<dir>    scratch directory (default: a new mktemp dir)
#         OUT=<file>    evidence file (default: the feature's evidence/bookworm-build.txt)
#         UTILS=<path>  cuems-utils checkout (default: ../cuems-utils)
#         MIRROR=<url>  Debian mirror (default: http://deb.debian.org/debian)
#         UV=<path>     uv to build the wheel with (default: uv); else PYTHON -m pip
# Needs:  mmdebstrap, newuidmap/newgidmap, uv or pip3, git; /etc/subuid and
#         /etc/subgid ranges for the calling user; network to the mirror and PyPI.
# Exit:   0 if the .deb built, pyvenv.cfg says home = /usr/bin, and the chroot
#         python3 is 3.11.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${WORK:-$(mktemp -d -t cuems-editor-bookworm-XXXXXX)}"
OUT="${OUT:-$REPO/specs/001-cuems-utils-migration/evidence/bookworm-build.txt}"
UTILS="${UTILS:-$REPO/../cuems-utils}"
MIRROR="${MIRROR:-http://deb.debian.org/debian}"

log() { printf '[bookworm-build] %s\n' "$*" >&2; }

for tool in mmdebstrap newuidmap newgidmap git tar dpkg-parsechangelog dpkg-deb; do
    command -v "$tool" >/dev/null 2>&1 || { log "missing required tool: $tool"; exit 2; }
done
grep -q "^$(id -un):" /etc/subuid && grep -q "^$(id -un):" /etc/subgid \
    || { log "no /etc/subuid or /etc/subgid range for $(id -un)"; exit 2; }

mkdir -p "$WORK"/{wheels,build/src}
log "work directory: $WORK"

UTILS_COMMIT="$(git -C "$UTILS" rev-parse HEAD)"
UTILS_DIRTY=""
[ -n "$(git -C "$UTILS" status --porcelain)" ] && UTILS_DIRTY=" (+ uncommitted changes)"
log "building the cuemsutils wheel from ../cuems-utils @ ${UTILS_COMMIT:0:7}$UTILS_DIRTY"
# A pyenv shim can exist and still refuse to run inside a checkout pinned to
# another interpreter, so "is it on PATH" is not the test; "does it run there" is.
UV="${UV:-uv}"
if (cd "$UTILS" && "$UV" --version) >/dev/null 2>&1; then
    (cd "$UTILS" && "$UV" build --wheel --out-dir "$WORK/wheels") > "$WORK/wheel.log" 2>&1
else
    (cd "$UTILS" && "${PYTHON:-python3}" -m pip wheel --no-deps -w "$WORK/wheels" .) > "$WORK/wheel.log" 2>&1
fi
WHEEL="$(basename "$(ls "$WORK"/wheels/cuemsutils-*.whl | head -1)")"
cp "$WORK/wheels/$WHEEL" "$WORK/build/"

EDITOR_COMMIT="$(git -C "$REPO" rev-parse HEAD)"
EDITOR_DIRTY=""
[ -n "$(git -C "$REPO" status --porcelain -- src debian pyproject.toml)" ] && EDITOR_DIRTY=" (+ uncommitted changes)"
git -C "$REPO" ls-files -co --exclude-standard -z \
    | tar -C "$REPO" --null -T - -cf - | tar -C "$WORK/build/src" -xf -
VERSION="$(cd "$WORK/build/src" && dpkg-parsechangelog -SVersion)"
log "building cuems-editor $VERSION from ${EDITOR_COMMIT:0:7}$EDITOR_DIRTY"

cat > "$WORK/build/build.sh" <<'BUILD'
#!/bin/sh
# Runs inside the bookworm chroot.
set -e
export DEBIAN_FRONTEND=noninteractive
B=/tmp/build
mkdir -p $B/out
apt-get -y --no-install-recommends install \
    dh-virtualenv debhelper dpkg-dev fakeroot build-essential \
    python3-all python3-dev python3-pip python3-setuptools python3-venv \
    > $B/apt.log 2>&1
{
    . /etc/os-release; echo "os: $PRETTY_NAME"
    echo "python3: $(command -v python3) -> $(readlink -f "$(command -v python3)") $(python3 --version 2>&1)"
    dpkg-query -W -f='dh-virtualenv ${Version}\n' dh-virtualenv
    dpkg-query -W -f='debhelper ${Version}\n' debhelper
} > $B/out/versions.txt

cd $B/src
export PIP_FIND_LINKS=$B PIP_DISABLE_PIP_VERSION_CHECK=1
# Pass 1: build, then only the dh_virtualenv step, to see the venv's pyvenv.cfg
# before override_dh_fixperms removes it. (dh dropped --until, #932537.)
( fakeroot debian/rules build \
  && fakeroot debian/rules override_dh_virtualenv \
  && cp debian/cuems-editor/usr/lib/cuems/pyvenv.cfg $B/out/pyvenv.cfg ) > $B/out/pass1.log 2>&1 \
  && echo "pass1 OK" >> $B/out/result.txt || echo "pass1 FAILED" >> $B/out/result.txt
fakeroot debian/rules clean > $B/out/clean.log 2>&1 || true
# Pass 2: the real build.
dpkg-buildpackage -b -us -uc -rfakeroot > $B/out/build.log 2>&1 \
  && echo "build OK" >> $B/out/result.txt || echo "build FAILED" >> $B/out/result.txt
cp $B/*.deb $B/out/ 2>/dev/null || true
exit 0
BUILD

mmdebstrap --mode=unshare --variant=apt --include=ca-certificates \
    --customize-hook='mkdir -p "$1/tmp/build"' \
    --customize-hook="copy-in $WORK/build/src $WORK/build/$WHEEL $WORK/build/build.sh /tmp/build" \
    --customize-hook='chroot "$1" sh /tmp/build/build.sh' \
    --customize-hook="copy-out /tmp/build/out $WORK/build" \
    bookworm /dev/null "$MIRROR" > "$WORK/build/mmdebstrap.log" 2>&1 \
    || { log "build chroot failed — see $WORK/build/mmdebstrap.log"; exit 1; }

R="$WORK/build/out"
DEB="$(ls "$R"/cuems-editor_"$VERSION"_*.deb 2>/dev/null | head -1 || true)"
HOME_LINE="$(grep -E '^home *=' "$R/pyvenv.cfg" 2>/dev/null || echo 'home = <missing>')"
PY_LINE="$(grep '^python3:' "$R/versions.txt" 2>/dev/null || echo 'python3: <unknown>')"

{
    echo "# T044 — cuems-editor built inside an unprivileged bookworm chroot (mmdebstrap --mode=unshare)."
    echo "# Script: tests/packaging/bookworm-build.sh. Not debuild on the trixie host."
    echo "date: $(date -Iseconds)"
    echo "host: $(. /etc/os-release; echo "$PRETTY_NAME"), mmdebstrap $(mmdebstrap --version 2>/dev/null | awk '{print $2}')"
    echo "editor: ${EDITOR_COMMIT:0:7}$EDITOR_DIRTY, version $VERSION"
    echo "cuemsutils wheel: $WHEEL from ../cuems-utils @ ${UTILS_COMMIT:0:7}$UTILS_DIRTY"
    echo
    echo "## chroot"
    cat "$R/versions.txt" 2>/dev/null || echo "(no versions.txt)"
    echo
    echo "## result"
    cat "$R/result.txt" 2>/dev/null || echo "(no result.txt)"
    echo
    echo "## pyvenv.cfg of the build venv (pass 1; debian/rules removes it from the package)"
    cat "$R/pyvenv.cfg" 2>/dev/null || echo "(missing)"
    echo
    echo "## the .deb"
    if [ -n "$DEB" ]; then
        echo "$(basename "$DEB")  sha256 $(sha256sum "$DEB" | cut -d' ' -f1)"
        dpkg-deb -f "$DEB" Package Version Architecture Depends
        echo
        echo "### contents (site-packages and bin only)"
        dpkg-deb -c "$DEB" | awk '{print $6}' | grep -E 'site-packages/[^/]+/?$|/bin/' | sort
    else
        echo "(no .deb)"
        echo; echo "### tail of build.log"; tail -40 "$R/build.log" 2>/dev/null || true
    fi
    echo
    echo "## checks"
    echo "pyvenv.cfg: $HOME_LINE"
    echo "$PY_LINE"
} > "$OUT"

log "evidence: $OUT"
[ -n "$DEB" ] || { log "no .deb"; exit 1; }
echo "$HOME_LINE" | grep -qE '^home *= */usr/bin$' || { log "pyvenv.cfg: $HOME_LINE"; exit 1; }
echo "$PY_LINE" | grep -q 'Python 3\.11\.' || { log "$PY_LINE"; exit 1; }
log "OK: $(basename "$DEB")"
