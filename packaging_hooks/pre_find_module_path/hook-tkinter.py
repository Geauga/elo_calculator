# packaging_hooks/pre_find_module_path/hook-tkinter.py
# Requirement: Keep Tkinter discoverable during the Windows package build.
"""Allow analysis of the bundled tkinter package."""


def pre_find_module_path(hook_api):
    """Keep the interpreter's normal tkinter search path."""


# Purpose: Prevent a false broken-Tkinter result from excluding the GUI module.
# Upstream: PyInstaller's pre-find hook calls this before module discovery.
# Upstream purpose: Decide whether tkinter can be analyzed for packaging.
# Environment: PyInstaller 6.22+ with bundled Python 3.12 on Windows.
# Generated: 2026-09-01 20:11 America/New_York.
# Changes: Preserve normal tkinter discovery for the project package build.
