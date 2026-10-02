"""Start CuemsWsServer on :9092 against a temporary library (T016, FR-003).

Same path as cli.run_manual, with three settings pointed at temp dirs so the
host's /opt/cuems_library, /tmp/cuems and /tmp/editor.ipc are not touched.
CUEMS_CONF_PATH must be set by the caller.
"""
import os, sys, tempfile
from cuemseditor.cli import get_settings, get_mappings, ensure_directories
from cuemseditor.CuemsWsServer import CuemsWsServer

root = sys.argv[1]
for sub in ('projects', 'media', 'trash/projects', 'trash/media', 'tmp', 'ipc'):
    os.makedirs(os.path.join(root, sub), exist_ok=True)
settings = get_settings()
settings['library_path'] = root
settings['tmp_path'] = os.path.join(root, 'tmp')
settings['editor_ipc'] = os.path.join(root, 'ipc', 'editor.ipc')
ensure_directories(settings)
CuemsWsServer(settings, get_mappings()).start(9092)
