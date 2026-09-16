Elo League Calculator v25 - Windows x64
======================================

Extract the ZIP, then double-click EloLeagueCalculator.exe.
Python does not need to be installed. No personal league data is included.

New in v25:
- Graph points display readable values; crowded labels are available on hover.
- Click a post-match graph point to select its source in Match History.
- Extreme finite Elo values no longer crash graphs; rank replay is faster.
- Ranking settings save through the existing backup, persistence and audit path,
  with rollback on failure. The settings dialog uses the active theme and fits
  its controls.
- Sequential, competition and dense rank modes are preserved in save files,
  historical rank graphs and exported season reports. Shared ranks require all
  selected priorities to tie; unique player names prevent shared ranks.
- Includes all previous season export, SB history, league settings, themes,
  multi-league, backup and audit features.

IMPORTANT SAVE COMPATIBILITY
This version writes schema 9. Existing supported saves (schemas 1-8) migrate
when loaded/saved, retaining any previously stored rank-sharing configuration.
Older executables cannot read schema 9. Back up the following directory before
upgrading, and do not use an older executable on upgraded data:
%LOCALAPPDATA%\EloLeagueCalculator

Built: September 15, 2026, America/New_York.
Source commit: f0346c328ccbb97a4274a20db43711371e291eef
Tools: Python 3.12.14, PyInstaller 6.22.2, Windows x64.
Verification: 130 tests passed with no skips, including real Tk graph, theme
and ranking-settings tests. Python, Tcl/Tk DLLs and script libraries, schema 9,
and the ranking-save/replay fixes were verified in the executable archive.
The executable reached GUI input idle using isolated temporary application data.
Startup verification is not a full manual UI acceptance test.

Executable SHA-256:
3E423C3B79B4222A0374BDDC97706AE436ECE3395EDE05438557C6A8766883AF
