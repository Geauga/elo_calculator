Elo League Calculator v26 - Windows x64
======================================

Extract the ZIP, then double-click EloLeagueCalculator.exe.
Python does not need to be installed. No personal league data is included.

New in v26:
- Optional conferences group and filter standings without changing Elo,
  opponents, graphs, or the league-wide simulator schedule.
- Conferences are disabled by default. Assignments are retained when the
  feature is disabled and follow player IDs through renames and roster edits.
- Season reports add conference standings only when conferences are enabled.
- Superscript, circled, and other non-decimal Unicode digits in player names no
  longer cause sorting or startup failures. Decimal digits still sort naturally.
- Includes all v25 graph values, graph-to-match links, ranking modes, historical
  rank improvements, themes, season export, backup, and audit features.

IMPORTANT SAVE COMPATIBILITY
This version writes schema 10. Existing supported saves (schemas 1-9) migrate
with conferences disabled and existing league settings retained. Older
executables, including v25, cannot read schema-10 saves. Back up the following
directory before upgrading, and do not use an older executable on upgraded data:
%LOCALAPPDATA%\EloLeagueCalculator

Built: September 25, 2026, America/New_York.
Source commit: a00bc7a512036c9fe6bd726f7bc753451bed7b9e
Tools: Python 3.12.14, PyInstaller 6.22.2, Windows x64.
Verification: The full suite discovered 148 tests; 129 executable tests passed.
Nineteen source GUI tests were skipped because the development runtime could not
initialize Tcl, although all 148 tests passed on the integrated source before
this build. The packaged archive contains Python, Tcl/Tk DLLs and script
libraries. Raw and ZIP-extracted executables reached GUI input idle using
separate isolated application data. Startup verification is not a full manual
UI acceptance test.

Executable SHA-256:
9FE68303ED9383050B91B91A4B71D5339B33AB65FC0F0081853EF4C908541C61
