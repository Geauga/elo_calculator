# Adjustable-Player Elo League

A Python desktop program for first-to-three leagues with adjustable rosters.

## Rules

- New leagues default to 12 players, and each league can independently use
  between 2 and 64 players. Every added player begins at `1500.00` Elo.
- Reducing a roster removes players from its end, drops their matches, and
  recalculates retained results. A confirmation and automatic backup protect
  the change.
- The K-factor is `32`.
- Ratings retain full decimal precision and display two decimal places.
- Standings show match wins and losses, match win percentage, individual game
  wins and losses, and game win percentage for first-to-three results.
- A 3-2 result applies 50% of the normal Elo change.
- A 3-1 result applies 75% of the normal Elo change.
- A 3-0 result applies 100% of the normal Elo change.
- The Settings button switches between persistent Windows-style light and dark
  themes.
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
