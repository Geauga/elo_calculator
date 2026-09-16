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
  theme. Every observation on a line graph has a point with its exact result:
  configured-precision Elo, league rank, percentage, or SB. Labels are shown
  where they fit without overlapping; hover over any point to read its value.
  Click any post-match point to open and select its source in Match History.
  League Rank replays saved results for the current roster using current ranking
  priorities and names; unplayed players retain their actual ratings. Rank replay
  accumulates statistics instead of repeatedly scanning earlier matches. Graph
  ranges also support very large finite Elo settings without division by zero.
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
  history, including scores, Elo changes, K-factors, margin multipliers, and
  both participants' post-match SB scores.
- An automatic backup is created before every saved edit. The Backups window
  also supports manual snapshots and restoring any of the newest 50 backups.
- Match history includes both participants' post-match SB scores for every
  recorded result. The Activity log keeps an append-only record of match
  entries and undo actions with SB scores in a dedicated column, plus renames,
  resets, league management, theme changes, and backup actions. Older activity
  records remain compatible, and the activity view has a horizontal scrollbar.

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

League schema 9 preserves rank-sharing mode as well as Base Elo, victory-margin
K scaling, and standings priority. Schema-8 and older saves upgrade with compatible
defaults, retaining any previously saved ranking mode. Older executables reject
schema 9 instead of silently discarding ranking settings. Back up your data before
upgrading; do not open upgraded saves in an older executable.

The standings Settings menu's League Settings dialog saves ranking priorities and
sequential, competition, or dense rank sharing with the same backup and audit
protection as other league edits. Equal ranks require all selected priorities to
tie; including unique player names prevents shared ranks. Rank graphs and exported
season reports use the selected ranking mode.

## Standalone Windows package

The current packaged release is
`release/EloLeagueCalculator-v25-Windows-x64.zip`.
It contains `EloLeagueCalculator.exe` and `README.txt`; Python does not need to
be installed. Extract the ZIP, then double-click the executable to start it.
Version 25 includes graph hover values and match links, extreme-Elo graph fixes,
faster historical ranks, ranking-settings save/rollback and theme fixes, and
schema-9 rank-sharing persistence, plus the earlier season export and SB history.
It was built from source commit
`f0346c328ccbb97a4274a20db43711371e291eef` on September 15, 2026.
Older releases are preserved. Back up your application data before upgrading;
older executables cannot read schema-9 saves.

Package verification:

- Executable SHA-256:
  `3E423C3B79B4222A0374BDDC97706AE436ECE3395EDE05438557C6A8766883AF`
- ZIP SHA-256:
  `57711021408C8337DC75ABAE53BF86EB28EEAC5BFA5CDB2D8C820C88653C1BD1`
- Validation: 130 tests passed with no skips, including real Tk checks.
  Bundled Python/Tcl/Tk and ranking fixes were verified; raw and ZIP-extracted
  executables reached GUI input idle with isolated application data. This is
  not a full manual UI acceptance test.

## Test

```powershell
python -m unittest -v
```

Current source validation: 130 tests, including ranking-settings persistence,
rollback, schema migration, dialog styling, graph ranges, crowded labels and
hover values, click-handler cleanup, rank replay across every priority order,
graph-trace, season-report, SB-history, numeric-validation, and real Tk theme checks.
These changes are included in the v25 executable. Older packages are preserved.
