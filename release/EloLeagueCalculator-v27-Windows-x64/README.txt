Elo League Calculator v27 - Windows x64
======================================

Extract the ZIP, then double-click EloLeagueCalculator.exe.
Python does not need to be installed. No personal league data is included.

New in v27:
- Playoff bracket support. Added a dedicated Playoffs tab and bracket preview.
- Mathematical playoff clinch indicator. Standings will now display '(Clinched)' next to a player's name when they are mathematically guaranteed a playoff spot.
- Playoff matches can be set as rated (affecting Elo) or unrated (no Elo transfer) via a checkbox in the Record Match dialog.
- Includes all v26 features: optional conferences, Unicode-name sorting fixes, and previous UI components.

IMPORTANT SAVE COMPATIBILITY
This version writes schema 11. Existing supported saves migrate cleanly. Older
executables, including v26, cannot read schema-11 saves. Back up the following
directory before upgrading, and do not use an older executable on upgraded data:
%LOCALAPPDATA%\EloLeagueCalculator

Built: September 30, 2026, America/New_York.
Source commit: cd25a6c70507a4cc95affc29469223b93bd41a7e
Tools: Python 3.12.14, PyInstaller 6.22.2, Windows x64.
Verification: The full suite discovered 154 tests; all 154 tests passed.

Executable SHA-256:
CC4DA2EFC893954E9959E1CEEF79569C51CA22959E2F2A3CCCBB397D808C82A7
