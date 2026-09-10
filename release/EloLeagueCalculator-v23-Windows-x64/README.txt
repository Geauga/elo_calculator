Elo League Calculator v23 - Windows x64
=====================================

Extract the ZIP, then double-click EloLeagueCalculator.exe.
Python does not need to be installed. Keep the older release as a fallback,
but do not use older executables with a save upgraded to schema 8.

This build includes the September 9 theme and schema-8 source fixes:
- Light/dark notebook tabs, dropdown hover states and existing dropdown lists.
- Readable head-to-head bar labels, text selections, and information headings.
- Theme-aware scrollbars and persistent light/dark preferences.
- Configurable Base Elo, victory-margin K scaling, and standings priorities.
- Historical Elo replay, validation, and backup/recovery safety fixes.

League data, settings, backups, and the activity log are stored in:
%LOCALAPPDATA%\EloLeagueCalculator
The ZIP does not contain personal league data. Back up that data directory
before upgrading. Existing supported saves are migrated when loaded/saved.

Built: September 10, 2026, America/New_York.
Source commit: 230f4029f72e6257baed4c6af97cb832165f0af1
Build tools: Python 3.12.14, PyInstaller 6.22.0, Windows x64.
Verification: 98 tests passed, including real Tk theme checks; bundled runtime
and theme bytecode verified; isolated executable startup reached GUI input idle.
The startup check is not a full manual UI acceptance test.

Executable SHA-256:
3C628ABDDFB679929DFA0A59890E046CB05AAC9329DD3F565F029962A7697058
