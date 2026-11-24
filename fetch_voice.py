#!/usr/bin/env python3
"""Compatibility wrapper: fetch a voice note. Prints only the output path.
Usage: .venv/bin/python fetch_voice.py <message stanza id> [out_dir]   (see fetch_media.py)
"""
import json, os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run([sys.executable, os.path.join(here, "fetch_media.py"), *sys.argv[1:]], capture_output=True, text=True)
if r.returncode:
    sys.stderr.write(r.stderr); sys.exit(r.returncode)
print(json.loads(r.stdout)["path"])
