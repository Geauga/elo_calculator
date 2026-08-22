Elo League Calculator for Windows
=================================

Double-click EloLeagueCalculator.exe to start the program. Python does not
need to be installed.

The application stores all league data, backups, settings, and the audit log in:

%LOCALAPPDATA%\EloLeagueCalculator

Rules
-----
- New leagues default to 12 players. The Players button adjusts each league
  independently from 2 to 64 players; added players begin at 1500.00 Elo.
- Reducing a roster removes players from its end and their related matches,
  then recalculates retained results after confirmation and an automatic backup.
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
26A85A8B4A68EB572BA21C06DE66EEB879982B09A33E0281169ECB149B4DAB45
