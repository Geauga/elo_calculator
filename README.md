# Adjustable-Player Elo League

A Python desktop program for configurable first-to-N or custom-score leagues
with adjustable rosters.

## Rules

- New leagues default to 12 players, and each league can independently use
  between 2 and 64 players. Every added player begins at `1500.00` Elo.
- Reducing a roster removes players from its end, drops their matches, and
  recalculates retained results. A confirmation and automatic backup protect
  the change.
- League Settings sets a separate K-factor and Elo rounding precision for each
  league. New leagues default to K `32` and two decimal places; K can be
  `0.01` through `1000`, and precision can be zero through six places.
- Each match stores the K-factor and rounding used for its Elo transfer, so
  later rule changes do not alter its calculation during roster replay.
- A draw gives each player a 0.5 Elo result, updates both ratings, and contributes
  half of the opponent's match score to each player's SB score. Draws can be
  enabled or disabled independently for each league in League Settings.
- Standings show match wins, draws, and losses; match score percentage; individual game
  wins and losses, game win percentage, and a Sonneborn-Berger (SB) score. Elo
  remains the primary ranking key. Among players tied on Elo, head-to-head match
  score percentage is the secondary tiebreaker, followed by overall match score
  percentage, SB, game win percentage, and a natural player-name order.
- New leagues use first-to-three rules: 3-2 applies 50%, 3-1 applies 75%, and
  3-0 applies 100% of the normal Elo change.
- The Simulator button runs a read-only Monte Carlo single round-robin for the
  active First-to-N league. Every player meets once per simulated season;
  current Elo supplies game probabilities, while simulated rating changes use
  the league's K-factor, rounding, and score multipliers. Results show title
  probability, average rank, and average match and game records; players tied
  on every standings tiebreaker share title and rank credit. An optional
  random seed makes a run reproducible. **Apply One Season** records one
  concrete simulated round robin in the active league, with confirmation and
  an automatic backup before ratings and history are updated.
- The Graphs tab plots Elo, match score percentage, and SB history for the
  selected player, including draw-aware calculations and SB changes caused by
  later results from prior opponents. Its background, axes, grid, labels, and
  plot line follow the active theme.
- The league Settings button selects a separate match format for each league.
  First-to-N mode sets the games needed to win and the Elo multiplier for every
  possible losing score. Custom-score mode accepts any whole-number result
  where the winner's score is higher.
- In custom-score mode, a shutout applies 100% of the normal Elo change and the
  closest possible win applies 50%; intermediate margins scale proportionally.
  Either format can disable automatic Elo calculation while continuing to
  record match and game results.
- The global Settings menu switches between persistent Windows-style light and dark
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
- The Activity log tab keeps an append-only record of match entries (including SB scores), undo,
  renames, resets, league management, theme changes, and backup actions. It features a horizontal scrollbar to prevent truncation.

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

The current packaged release is
`release/EloLeagueCalculator-v20-Windows-x64.zip`.
It contains `EloLeagueCalculator.exe` and `README.txt`; Python does not need to
be installed. Extract the ZIP, then double-click the executable to start it.

Package verification:

- Executable SHA-256:
  `4BC4C422F437503663C6D673A8F4F9CCB194AC8D70BC23815681672F03150DF6`
- ZIP SHA-256:
  `6EBD27780D5D330D247BDA0C684F129B1764376D40B0E7CA3A1CA3B73B709554`
- Validation: 69 unit tests passed, followed by an isolated Windows
  launch test.

## Test

```powershell
python -m unittest -v
```
