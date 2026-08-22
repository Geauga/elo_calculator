Elo League Calculator for Windows
=================================

Double-click EloLeagueCalculator.exe to start the program. Python does not
need to be installed.

The application stores all league data, backups, settings, and the audit log in:

%LOCALAPPDATA%\EloLeagueCalculator

Rules
-----
- Twelve players begin at 1500.00 Elo.
- K-factor: 32.
- 3-2 applies 50% of the normal Elo change.
- 3-1 applies 75% of the normal Elo change.
- 3-0 applies 100% of the normal Elo change.
- Ratings retain full decimal precision.
- The Settings button switches between light and dark themes and remembers the
  selection between sessions.
- Reset league restores all ratings to 1500.00 and clears match history after a
  confirmation prompt. Player names and the theme are preserved.
- The top toolbar creates, renames, switches, and deletes independent leagues.
- Automatic snapshots are made before every saved edit. The Backups window can
  create manual snapshots and restore any of the newest 50 backups.
- The Activity log records all edits and is not erased by reset or restore.
- Match action buttons remain above the rating preview so they stay visible at
  enlarged Windows display scaling.

Existing eight-player save files are upgraded automatically by adding four new
players at 1500.00 without changing earlier ratings or match history.
Existing single-league data is migrated to League 1 automatically.

SHA-256 for EloLeagueCalculator.exe:
C9DDE68B3594DBEC372EF668EA1F1AA1CD23D5F443080231D189DF71A87AF541
