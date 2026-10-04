Elo League Calculator v28 - Windows x64
======================================

Extract the ZIP, then double-click EloLeagueCalculator.exe.
Python does not need to be installed. No personal league data is included.

New in v28:
- Added a Wins, Draws, and Losses graph (W-D-L) with themed colors and legends.
- Fixed a bug where playoff matches incorrectly affected historical ranks and playoff-position standings.
- Playoff brackets now accurately seed based on tiebreakers rather than only Elo.
- Includes all v27 features: playoff brackets, mathematical clinch indicators, and unrated playoffs.

IMPORTANT SAVE COMPATIBILITY
This version uses schema 11. Existing supported saves migrate cleanly. Older
executables, including v26, cannot read schema-11 saves. Back up the following
directory before upgrading, and do not use an older executable on upgraded data:
%LOCALAPPDATA%\EloLeagueCalculator

Built: October 1, 2026, America/New_York.
Source commit: 42a21b6d1b7a2d42b934ea2778f889c1692257d0
Tools: Python 3.12.14, PyInstaller 6.22.2, Windows x64.
Verification: The full suite discovered 163 tests; all 163 tests passed.

Executable SHA-256:
40FFF3E941E2078A8816DA11809C0ACB478628828C47B64A70E8FD4BACBD3570
