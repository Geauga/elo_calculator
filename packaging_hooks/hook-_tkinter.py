# packaging_hooks/hook-_tkinter.py
# Requirement: Bundle Tcl and Tk data in the Windows executable.
"""Collect Tcl/Tk data from the bundled Windows Python runtime."""

from pathlib import Path
import sys


TCL_ROOT = Path(sys.base_prefix) / "tcl"
datas = [
    (str(TCL_ROOT / "tcl8.6"), "_tcl_data"),
    (str(TCL_ROOT / "tk8.6"), "_tk_data"),
]

# Purpose: Supply Tcl/Tk script libraries when PyInstaller cannot detect them.
# Upstream: EloLeagueCalculator.spec registers this project hook directory.
# Upstream purpose: Package a standalone Tkinter desktop application.
# Environment: PyInstaller 6.22+ with bundled Python 3.12 on Windows.
# Generated: 2026-09-01 20:11 America/New_York.
# Changes: Collect tcl8.6 and tk8.6 into PyInstaller's runtime directories.
