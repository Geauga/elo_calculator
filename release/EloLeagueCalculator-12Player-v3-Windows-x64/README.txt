Elo League Calculator for Windows
=================================

Double-click EloLeagueCalculator.exe to start the program. Python does not
need to be installed.

The application automatically saves its player names, ratings, and match
history here:

%LOCALAPPDATA%\EloLeagueCalculator\elo_league_data.json

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

Existing eight-player save files are upgraded automatically by adding four new
players at 1500.00 without changing earlier ratings or match history.

SHA-256 for EloLeagueCalculator.exe:
18F0BCF9249F49E9D20C7581D95034344112C68D4335DC9FC922A0B9F8E9DBBE
