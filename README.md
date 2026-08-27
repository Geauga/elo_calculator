# Adjustable-Player Elo League

A Python desktop program for configurable first-to-N or custom-score leagues
with adjustable rosters.

## Rules

- New leagues default to 12 players, and each league can independently use
  between 2 and 64 players. Every added player begins at `1500.00` Elo.
- Reducing a roster removes players from its end, drops their matches, and
  recalculates retained results. A confirmation and automatic backup protect
  the change.
- The K-factor is `32`.
- Ratings retain full decimal precision and display two decimal places.
- Standings show match wins and losses, match win percentage, individual game
  wins and losses, game win percentage, and a Sonneborn-Berger (SB) score. Elo
  remains the primary ranking key; equal Elo ratings are ordered by SB score.
- New leagues use first-to-three rules: 3-2 applies 50%, 3-1 applies 75%, and
  3-0 applies 100% of the normal Elo change.
- Edit Rules selects a separate match format for each league. First-to-N mode
  sets the games needed to win and the Elo multiplier for every possible losing
  score. Custom-score mode accepts any whole-number result where the winner's
  score is higher.
- In custom-score mode, a shutout applies 100% of the normal Elo change and the
  closest possible win applies 50%; intermediate margins scale proportionally.
  Either format can disable automatic Elo calculation while continuing to
  record match and game results.
- The Settings button switches between persistent Windows-style light and dark
  themes.
- All app-owned prompts, confirmations, warnings, and management windows use
  the same theme, Segoe UI typography, spacing, control styles, centering, and
  high-DPI scaling. Supported Windows versions also match each window's title
  bar to the selected light or dark theme.
- The Reset league button restores every rating to 1500.00 and clears match
  records after confirmation, while keeping player names and the chosen theme.
- Create, rename, switch between, and delete independent leagues from the top
  toolbar. Each league has its own players, ratings, standings, and history.
- An automatic backup is created before every saved edit. The Backups window
  also supports manual snapshots and restoring any of the newest 50 backups.
- The Activity log tab keeps an append-only record of match entries, undo,
  renames, resets, league management, theme changes, and backup actions.

## Run

Install Python 3.10 or newer with Tkinter, then run:

```powershell
python elo_calculator.py
```

The program automatically saves player names, ratings, and match history in the
current user's local application-data folder. Use **Undo last** to remove the
most recent match and restore both previous ratings.

Save files created by the earlier eight-player version are upgraded
automatically by retaining the original league and adding Players 9 through 12.
The previous single-league database is also upgraded automatically to
`League 1`, preserving its standings and match history.

## Standalone Windows package

The packaged version is distributed as `EloLeagueCalculator.exe`. It does not
require Python to be installed. Double-click the executable to start it.

## Test

```powershell
python -m unittest -v
```
