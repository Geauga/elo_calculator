Elo League Calculator v24 - Windows x64
======================================

Extract the ZIP, then double-click EloLeagueCalculator.exe.
Python does not need to be installed. Keep the older release as a fallback,
but do not use older executables with a save upgraded to schema 8.

This build includes all source features through September 11, 2026:
- Export Season saves league rules, final standings, statistics, and complete
  match history to a UTF-8 text document.
- Exported matches include scores, before/after Elo, transfers, K-factors,
  margin multipliers, rated state, and both participants' post-match SB scores.
- Match History and Activity Log show structured post-match SB scores.
- Graphs include point markers and League Rank history.
- Configurable Base Elo, K-factor scaling, Elo precision, match formats,
  draws, standings priorities, and variable player counts.
- Persistent light/dark themes, backups, multi-league data, and audit logging.
- Rank-history, numeric validation, persistence, and recovery safety fixes.

League data, settings, backups, and the activity log are stored in:
%LOCALAPPDATA%\EloLeagueCalculator
The ZIP does not contain personal league data. Back up that data directory
before upgrading. Existing supported saves are migrated when loaded/saved.

Built: September 11, 2026, America/New_York.
Source commit: 7d015441b7166193cbc7fb7045ed0483e33bb0c3
Build tools: Python 3.12.14, PyInstaller 6.22.2, Windows x64.
Verification: 111 tests passed with no skips; bundled Tcl/Tk was collected;
the isolated executable startup reached GUI input idle. The startup check is
not a full manual UI acceptance test.

Executable SHA-256:
0303D109B0B4CAD0200518A96E08C15B346AC3D39A0DD4BCD183CB72A9DE898C
