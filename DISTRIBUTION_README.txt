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
- The league Settings button sets a separate K-factor and Elo rounding precision for each
  league. Defaults are K 32 and two decimal places; supported values are K
  0.01 through 1000 and zero through six decimal places.
- New leagues use first-to-three rules: 3-2 applies 50%, 3-1 applies 75%, and
  3-0 applies 100% of the normal Elo change.
- The Simulator button runs read-only Monte Carlo single round-robin seasons
  for the active First-to-N league. It uses current Elo for game probabilities
  and the league's Elo settings for simulated rating changes, then reports
  title probability, average rank, and average match and game records. An
  optional random seed makes results reproducible.
- The league Settings button selects first-to-N or custom scores separately for every league.
  First-to-N lets you set the target and each losing-score multiplier. Custom
  scores accepts any whole-number result where the winner's score is higher.
- With custom scores, a shutout applies 100% of the normal Elo change, the
  closest possible win applies 50%, and intermediate margins scale
  proportionally. Either format can disable automatic Elo calculation while
  continuing to record results.
- Each match stores the K-factor and rounding used for its Elo transfer, so
  later rule changes do not alter historical calculations during roster replay.
- A draw gives both players a 0.5 Elo result using the league's K-factor and
  rounding, and contributes half the opponent's match score to SB. Draws can
  be enabled or disabled independently for each league in League Settings.
- Standings include match W-D-L, match score percentage, individual game W-L,
  game win percentage, and SB. For example, a 3-2 result records five games.
- The Graphs tab plots Elo, match score percentage, and SB history for the
  selected player, including draw-aware percentage and SB calculations.
- The global Settings menu switches between light and dark themes and remembers the
  selection between sessions.
- Prompts, confirmations, warnings, and management windows consistently follow
  the selected theme, typography, spacing, and Windows display scaling. Window
  title bars also follow the selected theme on supported Windows versions.
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
4E87C4614FFCE9B6799B5815E714538F6801CA980AC754566907D49A8CFF52C0
