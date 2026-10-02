"""Capture initial_mappings without CuemsWsServer.__init__ (T009).

__init__ still calls create_script() at this commit, so the server is built
with __new__ and given exactly what __init__ would have set: mappings_dict from
cli.get_mappings(), then reload_network_map_nodes(), then the frame from
initial_setting_message(). CUEMS_CONF_PATH points at this directory.
"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
os.environ['CUEMS_CONF_PATH'] = here
import cuemsutils
from cuemseditor.cli import get_mappings
from cuemseditor.CuemsWsServer import CuemsWsServer

server = CuemsWsServer.__new__(CuemsWsServer)
server.mappings_dict = get_mappings()
ok = server.reload_network_map_nodes()
server.nodeconf_available = lambda: False   # pin the live sample; /tmp/nodeconf.ipc is host state
frame = server.initial_setting_message()
print(json.dumps({'lib': cuemsutils.__version__, 'file': cuemsutils.__file__, 'reload_ok': ok}), file=sys.stderr)
print(frame)
