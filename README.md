# Adjustable-Player Elo League

A Python desktop program for configurable first-to-N or custom-score leagues
with adjustable rosters.

## Community

Read the [contribution guide](CONTRIBUTING.md), [code of conduct](CODE_OF_CONDUCT.md),
and [support guide](SUPPORT.md) before participating. Use the
[issue forms](https://github.com/Geauga/elo_calculator/issues/new/choose) for bugs,
feature requests, and usage questions. Report vulnerabilities privately as
described in the [security policy](SECURITY.md).

A project license has not yet been selected; these community documents do not
change the licensing of the code or bundled third-party components.

## Rules

- Playoffs: League Settings controls bracket size, **Single elimination** or
  **Double elimination**, and whether playoff matches affect Elo. Use **0** to
  disable playoffs, or choose **2-64** entrants (clamped to the roster).
  In the **Playoffs** tab, click a ready match or select it from the dropdown and
  choose **Record bracket result**. Select the winner and enter the score using
  the league's First-to-N or custom-score rules. Winners advance automatically;
  double elimination has separate winners' and losers' brackets, elimination
  after the second loss, and a grand-final reset when the losers' finalist wins
  the first final. Byes advance without recording a loss or changing Elo.
  Both brackets and all rounds have horizontal/vertical scrolling and follow
  the light/dark theme. Winner names are bold on completed match cards.
  Seeds lock on the first bracket result and survive restarts, rating changes,
  and renames. Undo last reopens the affected match; undoing all bracket results
  unlocks the seeds. Reset league clears the tournament. Removing a seeded
  player clears bracket progress while retaining any surviving historical results.
  Size/format changes are blocked while bracket results exist.
  Manual results entered using **Playoff match** retain their earlier behavior
  and do not advance the bracket; draws are allowed there if enabled, whereas
  bracket matches require a winner.
  Unrated playoffs leave ratings unchanged in both the preview and saved result.
  Playoff results do not count toward regular-season match/game statistics or
  head-to-head tiebreakers; rated playoff Elo changes still affect Elo-based ranks.
  Rank history follows the same rule. Basic playoff support is included in v27;
  progressing single/double-elimination brackets are source-only updates.
- Current source uses the league's configured standings order for bracket seeds.
  **Playoff position** marks the current top players in that order, not a
  guaranteed berth: no fixed season schedule or remaining-match limit is stored.
  Repeated opponents do not imply that a season is complete. Conference filters
  do not change these league-wide seeds, and shared ranks still fill only the
  configured number of slots, using the existing standings order for ties.

- Conferences are optional and **off by default**, including when loading an
  older league. In the main **Settings > Conferences...** dialog, enable them
  for the active league and assign a conference name to each player. Blank
  names leave players unassigned. Edits are saved when you select another
  player or click **Save conferences**; Cancel discards the dialog's edits.
- When enabled, the Standings selector offers All players, each named conference,
  and Unassigned players. A conference view ranks only its members using the
  league's ranking rules; statistics still include all league matches. The
  overall standings and League Rank graph remain league-wide. Conference
  standings are also included in season exports.
- Conferences do not change Elo calculations, allowed opponents, or simulator
  scheduling. Turning them off hides the selector but retains assignments.
  Names are case-insensitive, up to 40 characters; new players start unassigned.

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
- The Graphs tab plots Elo, league rank, cumulative match W-D-L, match score
  percentage, game win percentage, SB history, and head-to-head records for the
  selected player. The W-D-L view counts only regular-season results, matching
  the standings, and uses separate themed lines for wins, draws and
  losses; hover shows the full record and each result point opens its source
  match. Elo plots begin at
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

Current source writes league schema 12, preserving bracket format, frozen seeds
and result routing along with playoff settings, conferences, rank sharing, Base
Elo, victory-margin K scaling, and standings priority. Schemas 1-11 remain readable;
old leagues default to single elimination with no linked bracket results. Older saves default to
playoffs disabled, and schemas 1-9 also default to conferences disabled.
The v29 executable uses schema 12 and cannot open schema-12 saves. Back up your
data before upgrading; do not open upgraded saves in an older executable, including v26.
The playoff Elo fix applies to newly recorded results; it does not automatically
rewrite ratings or match transfers already saved by the earlier buggy source.

The standings Settings menu's League Settings dialog saves ranking priorities and
sequential, competition, or dense rank sharing with the same backup and audit
protection as other league edits. Equal ranks require all selected priorities to
tie; including unique player names prevents shared ranks. Rank graphs and exported
season reports use the selected ranking mode.

## Standalone Windows package

The current packaged release is
`release/EloLeagueCalculator-v28-Windows-x64.zip`.
It contains `EloLeagueCalculator.exe` and `README.txt`; Python does not need to
be installed. Extract the ZIP, then double-click the executable to start it.
Version 28 adds a Wins, Draws, and Losses graph, fixes playoff position logic,
and ensures proper seeding in playoff brackets. It also includes the v27
features like rated/unrated playoff toggles and earlier fixes.
It was built from source commit
`42a21b6d1b7a2d42b934ea2778f889c1692257d0` on October 1, 2026.
Older releases are preserved. Back up your application data before upgrading;
older executables, including v26, cannot read schema-11 saves.

Package verification:

- Executable SHA-256:
  `FF54EF08495DC17FBC5B5F28E628E0FB307FF82C609757A01CEF64D60D7BA98C`
- ZIP SHA-256:
  `472635E01E44C9C9DE0133A5F54F9D5762A2318E50636C465529EE612DA7C5A3`
- Validation: The full suite discovered 179 tests; all 179 tests passed on the
  integrated source before this build. The package contains Python and Tcl/Tk;
  raw and ZIP-extracted builds reached GUI input idle with isolated application data.
  This is not a full manual UI acceptance test.

## Test

```powershell
python -m unittest -v
```

Current source validation: 179 tests passed with no skips, including real Tk UI checks. Coverage
also verifies complete single/double-elimination runs for every field size 2-64,
two-loss elimination, both grand-final outcomes, byes, frozen seeds, save/reload,
undo/reset/roster changes, rollback, and bracket controls/themes/scrolling. It
includes cumulative W-D-L graph history, three-series rendering and match links,
playoff exclusion with original match indexes, bracket/position consistency,
custom priorities, repeated opponents, shared ranks and conference filters,
playoff Elo previews, save/replay, first-round byes and rank-history consistency,
plus optional conference defaults, migration, assignments, filtered ranks,
unchanged scheduling, full UI checks, ranking-settings persistence,
rollback, schema migration, dialog styling, graph ranges, crowded labels and
hover values, click-handler cleanup, rank replay across every priority order,
graph-trace, season-report, SB-history, numeric-validation, and real Tk theme checks.
The W-D-L graph and playoff position fixes are included in the
v29 executable, which uses schema 12. Older packages are preserved.
The progressing single/double-elimination brackets are source-only updates and
use schema 12; they are not included in the v29 executable.
