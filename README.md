# Adjustable-Player Elo League

A Python desktop program for configurable first-to-N or custom-score leagues
with adjustable rosters.

## Rules

- New leagues default to 12 players, and each league can independently use
  between 2 and 64 players. Every added player begins at that league's Base
  Elo, which defaults to `1500.00`.
- Reducing a roster removes players from its end, drops their matches, and
  recalculates retained results. A confirmation and automatic backup protect
  the change.
- League Settings sets a separate Base Elo, K-factor, optional victory-margin
  K scaling, Elo rounding precision, and standings priority for each league.
  New leagues default to Base Elo `1500`, K `32`, and two decimal places; K can
  be `0.01` through `1000`, and precision can be zero through six places. Base
  Elo controls later resets and added players without retroactively shifting
  existing results.
- Each match stores the K-factor, effective score/scaling multiplier, and
  rounding used for its Elo transfer, so later rule changes do not alter its
  calculation during roster replay.
- A draw gives each player a 0.5 Elo result, updates both ratings, and contributes
  half of the opponent's match score to each player's SB score. Draws can be
  enabled or disabled independently for each league in League Settings.
- Standings show match W-D-L when draws are enabled and W-L when draws are
  disabled, plus match score percentage, individual game wins and losses, game
  win percentage, and a Sonneborn-Berger (SB) score. By default, Elo
  is the primary ranking key. Among players tied on Elo, head-to-head match
  score percentage is the secondary tiebreaker and head-to-head game percentage
  is third, followed by overall match score percentage, SB, overall game win
  percentage, and a natural player-name order. League Settings can reorder the
  top-level Rating, Match %, SB, Game %, and Name priorities; head-to-head
  comparisons remain attached to Rating for players tied at the displayed Elo
  precision.
- New leagues use first-to-three rules: 3-2 applies 50%, 3-1 applies 75%, and
  3-0 applies 100% of the normal Elo change.
- The Simulator button runs a read-only Monte Carlo single round-robin for the
  active First-to-N league. Every player meets once per simulated season;
  current Elo supplies game probabilities, while simulated rating changes use
  the league's K-factor, rounding, and score multipliers. Results show title
  probability, average rank, and average match and game records; players tied
  on match wins are separated by head-to-head match score and then head-to-head
  game percentage before the remaining season tiebreakers. Players tied on
  every tiebreaker share title and rank credit. An optional random seed makes
  a run reproducible. **Apply One
  Season** records one concrete simulated round robin in the active league,
  with confirmation and an automatic backup before ratings and history are
  updated.
- The Graphs tab plots Elo, league rank, match score percentage, game win percentage, SB
  history, and head-to-head records for the selected player. Elo plots begin at
  the player's actual saved starting rating; percentage calculations are
  draw-aware, and SB history reflects later results from prior opponents. Its
  background, axes, grid, labels, plot line, and point markers follow the active
  theme. Every observation on a line graph is marked with a visible point.
  League Rank replays saved results for the current roster using current ranking
  priorities and names; unplayed players retain their actual ratings.
- The league Settings button selects a separate match format for each league.
  First-to-N mode sets the games needed to win and the Elo multiplier for every
  possible losing score. Custom-score mode accepts any whole-number result
  where the winner's score is higher.
- In custom-score mode, a shutout applies 100% of the normal Elo change and the
  closest possible win applies 50%; intermediate margins scale proportionally.
  Either format can disable automatic Elo calculation while continuing to
  record match and game results.
- The global Settings menu switches between persistent Windows-style light and
  dark themes and selects which standings columns are visible.
- Source theme styling includes notebook tabs, dropdown hover/press states and
  previously opened dropdown lists, scrollbars, focused/unfocused text selections,
  information headings, and readable head-to-head bar labels. Theme changes do
  not require restarting the app. These fixes are included in the v23 executable.
- All app-owned prompts, confirmations, warnings, and management windows use
  the same theme, Segoe UI typography, spacing, control styles, centering, and
  high-DPI scaling. Supported Windows versions also match each window's title
  bar to the selected light or dark theme.
- The Reset league button restores every rating to the league's configured Base
  Elo and clears match records after confirmation, while keeping player names
  and the chosen theme.
- Create, rename, switch between, and delete independent leagues from the top
  toolbar. Each league has its own players, ratings, standings, and history.
- The Export Season button saves the active league as a UTF-8 text document with
  its rules, final standings, player statistics, and complete chronological match
  history, including scores, Elo changes, K-factors, and margin multipliers.
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

League schema 8 stores Base Elo, victory-margin K scaling, and standings
priority explicitly. Schema-7 and older saves are upgraded with compatible
defaults. Older executables reject schema 8 instead of silently discarding the
new settings.

## Standalone Windows package

The current packaged release is
`release/EloLeagueCalculator-v23-Windows-x64.zip`.
It contains `EloLeagueCalculator.exe` and `README.txt`; Python does not need to
be installed. Extract the ZIP, then double-click the executable to start it.
Version 23 includes the schema-8 and theme fixes described above, built from
source commit `230f4029f72e6257baed4c6af97cb832165f0af1` on September 10, 2026.
Older releases are preserved. Back up your application data before upgrading;
older executables cannot read schema-8 saves.
The current source additionally includes line-graph points, League Rank history,
and stricter numeric/score/ID validation. These later changes are not in v23.

Package verification:

- Executable SHA-256:
  `3C628ABDDFB679929DFA0A59890E046CB05AAC9329DD3F565F029962A7697058`
- ZIP SHA-256:
  `00013EF7BA06EF5EE3CBFAAF4B0EF6BF77A31BB13A7394D38A37E519E2D2BB92`
- Validation: 98 tests passed, including real Tk theme checks. The executable's
  bundled runtime and theme bytecode were verified; an isolated Windows startup
  check reached GUI input idle. This is not a full manual UI acceptance test.

## Test

```powershell
python -m unittest -v
```

Current source validation: 105 tests, including numeric validation, historical
rank regressions, and real Tk theme checks.
