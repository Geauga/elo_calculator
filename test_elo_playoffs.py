# test_elo_playoffs.py
# Request: Fix playoff Elo, duplicate bracket seeds, and rank-history inconsistencies.
"""Regression coverage for optional playoff results and first-round byes."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from elo_calculator import EloCalculatorApp, _player_rank_history, _playoff_seeds, _ranked_players
from elo_model import League
from elo_storage import LeagueCollection


class PlayoffRatingTests(unittest.TestCase):
    def test_unrated_wins_and_draws_preserve_ratings_through_replay_and_undo(self):
        for draw in (False, True):
            with self.subTest(draw=draw):
                league = League.new(4)
                league.playoff_size = 3
                league.players[0].rating = 1700.0
                before = [p.rating for p in league.players]
                match = (league.record_draw(0, 1, is_playoff=True) if draw else
                         league.record_match(0, 1, 0, is_playoff=True))
                self.assertFalse(match.rated)
                self.assertTrue(match.is_playoff)
                self.assertEqual(match.rating_change, 0.0)
                self.assertEqual([p.rating for p in league.players], before)
                restored = League.from_dict(league.to_dict())
                restored.resize_players(3)
                self.assertEqual([p.rating for p in restored.players], before[:3])
                self.assertEqual(restored.matches[0].rating_change, 0.0)
                self.assertTrue(restored.matches[0].is_playoff)
                restored.undo_last_match()
                self.assertEqual([p.rating for p in restored.players], before[:3])

    def test_previews_and_records_share_rating_policy(self):
        for auto in (False, True):
            for playoffs_rated in (False, True):
                for playoff in (False, True):
                    for draw in (False, True):
                        with self.subTest(auto=auto, rated=playoffs_rated,
                                          playoff=playoff, draw=draw):
                            league = League.new(3)
                            league.players[0].rating = 1700.0
                            league.calculate_elo = auto
                            league.playoffs_rated = playoffs_rated
                            before = league.to_dict()
                            preview = (league.preview_draw(0, 1, is_playoff=playoff) if draw else
                                       league.preview_match(0, 1, 0, is_playoff=playoff))
                            self.assertEqual(league.to_dict(), before)
                            match = (league.record_draw(0, 1, is_playoff=playoff) if draw else
                                     league.record_match(0, 1, 0, is_playoff=playoff))
                            rated = auto and (not playoff or playoffs_rated)
                            self.assertEqual(match.rated, rated)
                            self.assertEqual(match.rating_change, preview['change'])
                            self.assertEqual(match.rating_change != 0.0, rated)
                            self.assertEqual(league.players[0].rating, 1700 + match.rating_change)
                            restored = League.from_dict(league.to_dict())
                            restored.resize_players(2)
                            self.assertEqual([p.rating for p in restored.players],
                                             [p.rating for p in league.players[:2]])

    def test_invalid_playoff_flags_do_not_mutate_state(self):
        for value in (None, 0, 1, 'false', []):
            for draw in (False, True):
                league = League.new(2)
                before = league.to_dict()
                with self.subTest(value=value, draw=draw), self.assertRaises(ValueError):
                    if draw:
                        league.record_draw(0, 1, is_playoff=value)
                    else:
                        league.record_match(0, 1, 0, is_playoff=value)
                self.assertEqual(league.to_dict(), before)


class PlayoffRankTests(unittest.TestCase):
    def test_history_matches_standings_at_every_mixed_season_prefix(self):
        for rated in (False, True):
            for mode in ('sequential', 'competition', 'dense'):
                for priorities in (['rating'], ['match_pct'], ['sb_score'],
                                   ['game_pct'], ['rating', 'match_pct', 'sb_score', 'name']):
                    league = League.new(4)
                    league.playoffs_rated = rated
                    league.ranking_mode = mode
                    league.tiebreaker_hierarchy = priorities
                    expected = {p.id: [] for p in league.players}

                    def collect():
                        for rank, player in _ranked_players(league):
                            expected[player.id].append(rank)

                    collect()
                    for first, second, playoff, draw in (
                        (1, 0, True, False), (2, 1, False, False),
                        (0, 2, True, True), (3, 1, False, True),
                        (0, 3, False, False), (2, 0, True, False),
                    ):
                        if draw:
                            league.record_draw(first, second, is_playoff=playoff)
                        else:
                            league.record_match(first, second, 1, is_playoff=playoff)
                        collect()
                    before = deepcopy(league.to_dict())
                    for player in league.players:
                        with self.subTest(rated=rated, mode=mode, priorities=priorities,
                                          player=player.id):
                            self.assertEqual(_player_rank_history(league, player.id),
                                             expected[player.id])
                    self.assertEqual(league.to_dict(), before)


class PlayoffBracketTests(unittest.TestCase):
    def test_every_supported_size_uses_each_qualifier_once(self):
        for requested in range(2, 65):
            for roster_size in (requested, max(2, requested - 1)):
                with self.subTest(requested=requested, roster=roster_size):
                    app = object.__new__(EloCalculatorApp)
                    app.league = League.new(roster_size)
                    app.league.playoff_size = requested
                    for player in app.league.players:
                        player.rating -= player.id  # Unambiguous seeded order.
                    app.playoffs_canvas = Mock()
                    app.playoffs_canvas.winfo_width.return_value = 1000
                    app.playoffs_canvas.winfo_height.return_value = 800
                    app._refresh_playoffs_tab()
                    labels = [call.kwargs['text'] for call in
                              app.playoffs_canvas.create_text.call_args_list
                              if 'first_round' in call.kwargs.get('tags', ())]
                    entrants = [label for label in labels if '. Player ' in label]
                    self.assertCountEqual(entrants, [f'{i + 1}. Player {i + 1}'
                                                    for i in range(roster_size)])
                    slots = 1 << (roster_size - 1).bit_length()
                    self.assertEqual(labels.count('BYE'), slots - roster_size)


class PlayoffPositionTests(unittest.TestCase):
    @staticmethod
    def render(league, visible_ids=None):
        app = object.__new__(EloCalculatorApp)
        app.league = league
        app.standings = Mock()
        app.standings.selection.return_value = ()
        app.standings.get_children.return_value = ()
        app._conference_player_ids = Mock(return_value=visible_ids)
        app._refresh_standings()
        rows = {int(call.kwargs['iid']): call.kwargs['values'] for call in
                app.standings.insert.call_args_list}
        app.playoffs_canvas = Mock()
        app.playoffs_canvas.winfo_width.return_value = 900
        app.playoffs_canvas.winfo_height.return_value = 600
        app._refresh_playoffs_tab()
        labels = [call.kwargs['text'] for call in app.playoffs_canvas.create_text.call_args_list]
        return rows, labels

    def test_labels_match_bracket_when_match_points_and_elo_disagree(self):
        league = League.new(4)
        league.playoff_size = 2
        league.calculate_elo = False
        for player, rating in zip(league.players, (1000, 1600, 1550, 1500)):
            player.rating = rating
        for winner, loser in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
            league.record_match(winner, loser, 0)
        before = league.to_dict()
        rows, labels = self.render(league)
        self.assertEqual(rows[0][1], 'Player 1')
        self.assertEqual({p_id for p_id, row in rows.items()
                          if row[1].endswith(' (Playoff position)')}, {1, 2})
        self.assertIn('1. Player 2', labels)
        self.assertIn('2. Player 3', labels)
        self.assertFalse(any('Clinched' in row[1] for row in rows.values()))
        self.assertEqual(league.to_dict(), before)

    def test_repeated_opponents_do_not_guarantee_a_future_berth(self):
        league = League.new(4)
        league.playoff_size = 2
        league.calculate_elo = False
        league.tiebreaker_hierarchy = ['match_pct']
        for winner, loser in ((0, 1), (0, 1), (0, 1), (2, 3), (3, 2), (2, 3)):
            league.record_match(winner, loser, 0)
        rows, _ = self.render(league)
        self.assertEqual(rows[0][1], 'Player 1 (Playoff position)')
        for _ in range(8):
            league.record_match(1, 0, 0)
        rows, labels = self.render(league)
        self.assertEqual(rows[0][1], 'Player 1')
        self.assertNotIn('Player 1', ' '.join(labels))
        self.assertFalse(any('Clinched' in row[1] for row in rows.values()))

    def test_seed_order_uses_configured_priorities_and_natural_names(self):
        league = League.new(12)
        league.playoff_size = 3
        self.assertEqual([p.id for p in _playoff_seeds(league)], [0, 1, 2])
        league.calculate_elo = False
        league.tiebreaker_hierarchy = ['match_pct', 'name']
        league.record_match(10, 0, 0)
        league.record_match(2, 1, 0)
        rows, labels = self.render(league)
        self.assertEqual([p.id for p in _playoff_seeds(league)], [2, 10, 0])
        for seed, player in enumerate(_playoff_seeds(league), 1):
            self.assertIn(f'{seed}. {player.name}', labels)
            self.assertTrue(rows[player.id][1].endswith(' (Playoff position)'))

    def test_disabled_clamped_and_shared_rank_fields(self):
        league = League.new(4)
        league.tiebreaker_hierarchy = ['rating']
        for mode in ('sequential', 'competition', 'dense'):
            league.ranking_mode = mode
            for size in (0, 1, 2, 4, 8):
                with self.subTest(mode=mode, size=size):
                    league.playoff_size = size
                    self.assertEqual([p.id for p in _playoff_seeds(league)],
                                     list(range(min(size, 4))))
                    rows, _ = self.render(league)
                    marked = {p_id for p_id, row in rows.items()
                              if row[1].endswith(' (Playoff position)')}
                    self.assertEqual(marked, set(range(min(size, 4))))

    def test_conference_filter_does_not_change_league_wide_qualifiers(self):
        league = League.new(4)
        league.playoff_size = 2
        league.configure_conferences(True, {0: 'East', 1: 'West', 2: 'East', 3: 'West'})
        rows, labels = self.render(league, {0, 2})
        self.assertEqual(set(rows), {0, 2})
        self.assertEqual(rows[0][1], 'Player 1 (Playoff position)')
        self.assertEqual(rows[2][1], 'Player 3')
        self.assertIn('1. Player 1', labels)
        self.assertIn('2. Player 2', labels)


class TkPlayoffPreviewTests(unittest.TestCase):
    def test_checkbox_updates_preview_and_saved_result(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'Tk unavailable: {error}')
        root.withdraw()
        try:
            with TemporaryDirectory() as directory:
                folder = Path(directory)
                with patch.multiple(
                    'elo_calculator', DATA_FILE=folder / 'data.json',
                    SETTINGS_FILE=folder / 'settings.json',
                    BACKUP_DIRECTORY=folder / 'backups',
                    AUDIT_LOG_FILE=folder / 'audit.jsonl',
                    RECOVERY_DIRECTORY=folder / 'recovery',
                ), patch.object(EloCalculatorApp, '_set_title_bar_theme'):
                    app = EloCalculatorApp(root)
                    self.assertIn('Change: +/-16.00 Elo', app.preview_var.get())
                    app.playoff_check.invoke()
                    self.assertIn('Change: +/-0.00 Elo', app.preview_var.get())
                    app._record_match()
                    restored = LeagueCollection.load(folder / 'data.json').active.league
                    self.assertTrue(restored.matches[-1].is_playoff)
                    self.assertFalse(restored.matches[-1].rated)
                    self.assertEqual(restored.matches[-1].rating_change, 0.0)
                    app.playoff_check.invoke()
                    self.assertIn('Change: +/-16.00 Elo', app.preview_var.get())
        finally:
            root.update_idletasks()
            root.destroy()


if __name__ == '__main__':
    unittest.main()

# Purpose: Verify reviewed playoff fixes without touching real league data.
# Upstream: elo_model.py records results; elo_calculator.py renders previews,
# ranks and brackets; elo_storage.py persists leagues for reload/replay checks.
# Environment: Python 3.12 / Windows Tk 8.6.
# Generated: 2026-09-27 16:22 America/New_York. Changes: New playoff test suite.
# Review update: 2026-09-30 18:00 America/New_York; Python 3.12 / Windows Tk 8.6.
# Purpose: Keep current-position labels and bracket entrants aligned without
# claiming guaranteed berths for leagues with no fixed schedule.
# Upstream: elo_calculator.py ranks and renders players; elo_model.py owns results.
# Changed lines: import shared seeds; add PlayoffPositionTests for differing Elo/
# points, repeats, custom/natural ordering, ties, disabled/clamped fields and filters.
# Updated 2026-10-01 America/New_York: 129-131 check unique first-round seed labels
# while progressing brackets may show those players again in later rounds.
# Purpose/upstream/environment unchanged; double-elimination tests are separate.
