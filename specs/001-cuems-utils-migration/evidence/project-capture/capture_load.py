"""Capture CuemsDBProject.load_xml for a fixture, the way send_project serialises it."""
import json, sys, hashlib, os, shutil, tempfile, cuemsutils
from cuemseditor.CuemsDBProject import CuemsDBProject
fixture = sys.argv[1]
lib = tempfile.mkdtemp()
os.makedirs(os.path.join(lib, 'projects', 'p'))
dst = os.path.join(lib, 'projects', 'p', 'script.xml')
shutil.copy(fixture, dst)
p = CuemsDBProject.__new__(CuemsDBProject)
p.projects_path = os.path.join(lib, 'projects'); p.script_file_name = 'script.xml'; p.script_schema_name = 'script'
before = hashlib.sha256(open(dst,'rb').read()).hexdigest()
d = p.load_xml('p')
after = hashlib.sha256(open(dst,'rb').read()).hexdigest()
frame = json.dumps({"type": "project", "value": d})
print(json.dumps({"lib": cuemsutils.__version__, "file": cuemsutils.__file__, "before": before, "after": after}), file=sys.stderr)
print(frame)
