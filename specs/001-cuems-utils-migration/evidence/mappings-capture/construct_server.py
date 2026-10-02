import os
os.environ['CUEMS_CONF_PATH'] = os.path.dirname(os.path.abspath(__file__))
from cuemseditor.cli import get_settings, get_mappings
from cuemseditor.CuemsWsServer import CuemsWsServer
s = get_settings(); s['tmp_path'] = '' + __import__('tempfile').mkdtemp() + ''; s['editor_ipc'] = __import__('tempfile').mkdtemp() + '/editor.ipc'
import traceback, sys
try:
    CuemsWsServer(s, get_mappings())
except BaseException:
    traceback.print_exc(file=sys.stdout); sys.stdout.flush(); os._exit(1)
print('constructed')
