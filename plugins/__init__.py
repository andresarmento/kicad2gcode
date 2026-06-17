#!/usr/bin/env python3
# __init__.py
# Entry point for the Kicad2Gcode KiCad plugin.
# Registers two toolbar buttons: one for board cutting, one for drilling.
#
# Installation (Windows):
#   Copy the entire kicad_plugin/ folder to:
#   %APPDATA%\kicad\<version>\scripting\plugins\gerber2gcode\
#   Then restart KiCad (or run pcbnew.LoadPlugins() in the Scripting Console).
#
# Requires shapely in KiCad's Python:
#   "C:\Program Files\KiCad\<version>\bin\python.exe" -m pip install shapely

import os
import sys

plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from edgecuts2gcode import EdgeCuts2GcodePlugin
from drill2gcode import Drill2GcodePlugin

EdgeCuts2GcodePlugin().register()
Drill2GcodePlugin().register()
